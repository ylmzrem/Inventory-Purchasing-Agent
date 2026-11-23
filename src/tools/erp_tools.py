import uuid
import json
import hashlib
from datetime import datetime
from src.db.database import get_connection, DEFAULT_DB_PATH

def stok_sorgula(product_id: str, db_path=DEFAULT_DB_PATH) -> dict:
    """Ürünün fiziksel, bloke ve kullanılabilir stok miktarını zaman damgasıyla getirir."""
    conn = get_connection(db_path)
    row = conn.execute("""
        SELECT p.product_id, p.name, p.unit, p.safety_stock, p.reorder_point,
               p.min_order_qty, p.pack_multiple,
               i.physical_stock, i.allocated_stock, i.updated_at
        FROM products p
        JOIN inventory i ON p.product_id = i.product_id
        WHERE p.product_id = ?
    """, (product_id,)).fetchone()
    conn.close()

    if not row:
        return {"error": "UNKNOWN_PRODUCT", "message": f"Bilinmeyen ürün kodu: {product_id}"}

    data = dict(row)
    if data["physical_stock"] < 0 or data["allocated_stock"] < 0 or data["allocated_stock"] > data["physical_stock"]:
        return {
            "error": "INVALID_INVENTORY_RECORD",
            "message": "Stok kaydı hatalı veya tutarsız. Hesaplama durduruldu.",
            "raw": data
        }

    data["available_stock"] = data["physical_stock"] - data["allocated_stock"]
    return data

def talep_getir(product_id: str, start_date: str, end_date: str, db_path=DEFAULT_DB_PATH) -> dict:
    """Belirtilen tarih aralığındaki tarihli talepleri getirir; bloke stokla karşılananları ayırır."""
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT demand_id, demand_date, quantity, is_covered_by_allocation
        FROM demand_forecast
        WHERE product_id = ? AND demand_date BETWEEN ? AND ?
        ORDER BY demand_date ASC
    """, (product_id, start_date, end_date)).fetchall()
    conn.close()

    schedule = [dict(r) for r in rows]
    uncovered_total = sum(r["quantity"] for r in schedule if not r["is_covered_by_allocation"])
    return {
        "product_id": product_id,
        "start_date": start_date,
        "end_date": end_date,
        "total_uncovered_demand": uncovered_total,
        "schedule": schedule
    }

def acik_siparisler(product_id: str, db_path=DEFAULT_DB_PATH) -> dict:
    """Ürüne ait kesinleşmiş veya yoldaki açık siparişleri döndürür."""
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT po_id, quantity, expected_date, status
        FROM open_orders
        WHERE product_id = ? AND status IN ('CONFIRMED', 'IN_TRANSIT', 'DELAYED')
        ORDER BY expected_date ASC
    """, (product_id,)).fetchall()
    conn.close()
    return {"product_id": product_id, "open_orders": [dict(r) for r in rows]}

def tedarikci_listesi(product_id: str, db_path=DEFAULT_DB_PATH) -> dict:
    """Ürünü temin edebilen tedarikçileri, teslim sürelerini ve kademeli fiyatlarını getirir."""
    conn = get_connection(db_path)
    suppliers = conn.execute("""
        SELECT sp.id AS sp_id, s.supplier_id, s.name, s.reliability_score, s.notes,
               sp.lead_time_days, sp.min_order_qty, sp.pack_multiple,
               sp.freight_cost, sp.currency
        FROM supplier_products sp
        JOIN suppliers s ON sp.supplier_id = s.supplier_id
        WHERE sp.product_id = ?
    """, (product_id,)).fetchall()

    result = []
    for sup in suppliers:
        sup_dict = dict(sup)
        tiers = conn.execute("""
            SELECT min_qty, max_qty, unit_price
            FROM price_tiers
            WHERE supplier_product_id = ?
            ORDER BY min_qty ASC
        """, (sup_dict["sp_id"],)).fetchall()
        sup_dict["price_tiers"] = [dict(t) for t in tiers]
        del sup_dict["sp_id"]
        result.append(sup_dict)

    conn.close()
    return {"product_id": product_id, "suppliers": result}

def _compute_data_hash(product_id: str, db_path=DEFAULT_DB_PATH) -> str:
    snapshot = {
        "stock": stok_sorgula(product_id, db_path=db_path),
        "orders": acik_siparisler(product_id, db_path=db_path),
        "suppliers": tedarikci_listesi(product_id, db_path=db_path)
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()

def satin_alma_taslagi_olustur(
    product_id: str,
    supplier_id: str,
    quantity: float,
    total_cost: float,
    currency: str,
    required_date: str,
    expected_delivery_date: str,
    rationale: str,
    idempotency_key: str | None = None,
    db_path=DEFAULT_DB_PATH
) -> dict:
    """Kullanıcı onayına sunulmak üzere DRAFT durumunda satın alma talebi oluşturur."""
    conn = get_connection(db_path)
    if idempotency_key:
        existing = conn.execute(
            "SELECT req_id, status FROM purchase_requisitions WHERE idempotency_key = ?",
            (idempotency_key,)
        ).fetchone()
        if existing:
            conn.close()
            return {"req_id": existing["req_id"], "status": existing["status"], "duplicate": True}

    req_id = f"REQ-{uuid.uuid4().hex[:8].upper()}"
    snap_hash = _compute_data_hash(product_id, db_path=db_path)
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO purchase_requisitions
        (req_id, idempotency_key, product_id, supplier_id, quantity, total_cost, currency,
         required_date, expected_delivery_date, rationale, status, data_snapshot_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?)
    """, (
        req_id, idempotency_key, product_id, supplier_id, quantity, total_cost, currency,
        required_date, expected_delivery_date, rationale, snap_hash, now
    ))
    conn.commit()
    conn.close()
    return {
        "req_id": req_id,
        "product_id": product_id,
        "supplier_id": supplier_id,
        "quantity": quantity,
        "total_cost": total_cost,
        "currency": currency,
        "required_date": required_date,
        "expected_delivery_date": expected_delivery_date,
        "rationale": rationale,
        "status": "DRAFT"
    }

def satin_alma_talebi_kaydet(req_id: str, user_approved: bool, db_path=DEFAULT_DB_PATH) -> dict:
    """Yalnızca açık kullanıcı onayı varsa ve veriler değişmemişse talebi SAVED olarak kaydeder."""
    if not user_approved:
        return {"error": "APPROVAL_REQUIRED", "message": "Kullanıcı onayı olmadan kayıt yapılamaz."}

    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM purchase_requisitions WHERE req_id = ?", (req_id,)).fetchone()
    if not row:
        conn.close()
        return {"error": "NOT_FOUND", "message": f"Taslak bulunamadı: {req_id}"}

    req = dict(row)
    if req["status"] == "SAVED":
        conn.close()
        return {
            "error": "DUPLICATE_EXECUTION",
            "message": "Mükerrer işlem engellendi: Bu talep zaten kaydedilmiş.",
            "req_id": req_id,
            "status": "SAVED"
        }

    current_hash = _compute_data_hash(req["product_id"], db_path=db_path)
    if current_hash != req["data_snapshot_hash"]:
        conn.close()
        return {
            "error": "DATA_CHANGED",
            "message": "Taslak oluşturulduktan sonra stok, sipariş veya tedarikçi verisi değişti. Yeniden hesaplama ve onay gerekli."
        }

    conn.execute("UPDATE purchase_requisitions SET status = 'SAVED' WHERE req_id = ?", (req_id,))
    conn.commit()
    conn.close()
    return {
        "req_id": req_id,
        "status": "SAVED",
        "message": "Satın alma talebi test ortamına kaydedildi. Fiziksel stok artırılmadı."
    }
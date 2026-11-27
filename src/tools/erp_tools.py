import uuid
import json
import hashlib
import sqlite3
from datetime import datetime
from src.db.database import get_connection, DEFAULT_DB_PATH

def stok_sorgula(sku: str, db_path=DEFAULT_DB_PATH) -> dict:
    """Ürünün fiziksel, bloke ve kullanılabilir stok miktarını zaman damgasıyla getirir."""
    conn = get_connection(db_path)
    row = conn.execute("""
        SELECT p.sku, p.sku AS product_id, p.name, p.unit, p.pcs_per_unit,
               p.safety_stock, p.reorder_point, p.min_order_qty, p.pack_multiple,
               i.physical_stock, i.allocated_stock, i.updated_at
        FROM products p
        JOIN inventory i ON p.sku = i.sku
        WHERE p.sku = ?
    """, (sku,)).fetchone()
    conn.close()

    if not row:
        return {"error": "UNKNOWN_PRODUCT", "message": f"Bilinmeyen ürün kodu: {sku}"}

    data = dict(row)
    if data["physical_stock"] < 0 or data["allocated_stock"] < 0 or data["allocated_stock"] > data["physical_stock"]:
        return {
            "error": "INVALID_INVENTORY_RECORD",
            "message": "Stok kaydı hatalı veya tutarsız. İşlem durduruldu.",
            "raw": data
        }

    data["available_stock"] = data["physical_stock"] - data["allocated_stock"]
    return data

def talep_getir(sku: str, start_date: str, end_date: str, db_path=DEFAULT_DB_PATH) -> dict:
    """Belirtilen tarih aralığındaki tarihli talepleri getirir."""
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT demand_id, demand_date, quantity, is_covered_by_allocation
        FROM demand_forecast
        WHERE sku = ? AND demand_date BETWEEN ? AND ?
        ORDER BY demand_date ASC
    """, (sku, start_date, end_date)).fetchall()
    conn.close()

    schedule = [dict(r) for r in rows]
    uncovered_total = sum(r["quantity"] for r in schedule if not r["is_covered_by_allocation"])
    return {
        "sku": sku,
        "start_date": start_date,
        "end_date": end_date,
        "total_uncovered_demand": uncovered_total,
        "schedule": schedule
    }

def acik_siparisler(sku: str, db_path=DEFAULT_DB_PATH) -> dict:
    """Ürüne ait kesinleşmiş veya yoldaki açık siparişleri döndürür."""
    conn = get_connection(db_path)
    rows = conn.execute("""
        SELECT po_id, quantity, expected_date, status
        FROM open_orders
        WHERE sku = ? AND status IN ('CONFIRMED', 'IN_TRANSIT', 'DELAYED')
        ORDER BY expected_date ASC
    """, (sku,)).fetchall()
    conn.close()
    return {"sku": sku, "open_orders": [dict(r) for r in rows]}

def tedarikci_listesi(sku: str, db_path=DEFAULT_DB_PATH) -> dict:
    """Ürünü temin edebilen tedarikçileri, teslim sürelerini ve kademeli fiyatlarını getirir."""
    conn = get_connection(db_path)
    suppliers = conn.execute("""
        SELECT sp.id AS sp_id, s.supplier_id, s.name, s.reliability_score, s.notes,
               sp.lead_time_days, sp.lead_time_type, sp.min_order_qty, sp.pack_multiple,
               sp.freight_fixed, sp.freight_per_unit, sp.currency
        FROM supplier_products sp
        JOIN suppliers s ON sp.supplier_id = s.supplier_id
        WHERE sp.sku = ?
    """, (sku,)).fetchall()

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
    return {"sku": sku, "suppliers": result}

def _compute_data_hash(sku: str, start_date: str, end_date: str, db_path=DEFAULT_DB_PATH) -> str:
    """Stok, açık sipariş, tedarikçi ve dönemsel talep verilerinin tam özet hash'ini üretir."""
    snapshot = {
        "stock": stok_sorgula(sku, db_path=db_path),
        "demand": talep_getir(sku, start_date, end_date, db_path=db_path),
        "orders": acik_siparisler(sku, db_path=db_path),
        "suppliers": tedarikci_listesi(sku, db_path=db_path),
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()

def compute_approval_token(req_id: str, snapshot_hash: str) -> str:
    """Uygulama katmanının kullanıcı onayı anında üreteceği deterministik onay imzası."""
    payload = f"APPROVED:{req_id}:{snapshot_hash}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

def satin_alma_taslagi_olustur(
    sku: str,
    supplier_id: str,
    quantity: float,
    total_cost: float,
    currency: str,
    start_date: str,
    end_date: str,
    required_date: str,
    expected_delivery_date: str,
    rationale: str,
    idempotency_key: str | None = None,
    db_path=DEFAULT_DB_PATH
) -> dict:
    """Geçerli stok kontrolü yaptıktan sonra DRAFT durumunda satın alma talebi oluşturur."""
    stock_check = stok_sorgula(sku, db_path=db_path)
    if "error" in stock_check:
        return {
            "error": stock_check["error"],
            "message": f"Stok doğrulaması başarısız olduğu için taslak oluşturulamadı: {stock_check.get('message')}"
        }

    conn = get_connection(db_path)
    if idempotency_key:
        existing = conn.execute(
            "SELECT req_id, status, data_snapshot_hash FROM purchase_requisitions WHERE idempotency_key = ?",
            (idempotency_key,)
        ).fetchone()
        if existing:
            conn.close()
            return {
                "req_id": existing["req_id"],
                "status": existing["status"],
                "snapshot_hash": existing["data_snapshot_hash"],
                "duplicate": True
            }

    req_id = f"REQ-{uuid.uuid4().hex[:8].upper()}"
    snap_hash = _compute_data_hash(sku, start_date, end_date, db_path=db_path)
    now = datetime.now().isoformat()

    conn.execute("""
        INSERT INTO purchase_requisitions
        (req_id, idempotency_key, sku, supplier_id, quantity, total_cost, currency,
         start_date, end_date, required_date, expected_delivery_date, rationale, status, data_snapshot_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'DRAFT', ?, ?)
    """, (
        req_id, idempotency_key, sku, supplier_id, quantity, total_cost, currency,
        start_date, end_date, required_date, expected_delivery_date, rationale, snap_hash, now
    ))
    conn.commit()
    conn.close()
    return {
        "req_id": req_id,
        "sku": sku,
        "supplier_id": supplier_id,
        "quantity": quantity,
        "total_cost": total_cost,
        "currency": currency,
        "start_date": start_date,
        "end_date": end_date,
        "required_date": required_date,
        "expected_delivery_date": expected_delivery_date,
        "rationale": rationale,
        "snapshot_hash": snap_hash,
        "status": "DRAFT"
    }

def satin_alma_talebi_kaydet(
    req_id: str,
    approval_token: str | None = None,
    db_path=DEFAULT_DB_PATH
) -> dict:
    """
    Yalnızca uygulama katmanından gelen geçerli kullanıcı onay imzası (approval_token) varsa
    ve veriler değişmemişse atomik SQLite transaction ile talebi SAVED durumuna geçirir.
    """
    if not approval_token:
        return {
            "error": "APPROVAL_REQUIRED",
            "message": "Uygulama katmanından doğrulanmış kullanıcı onay imzası (approval_token) olmadan kayıt yapılamaz."
        }

    conn = get_connection(db_path)
    try:
        conn.isolation_level = None
        conn.execute("BEGIN IMMEDIATE")

        row = conn.execute("SELECT * FROM purchase_requisitions WHERE req_id = ?", (req_id,)).fetchone()
        if not row:
            conn.execute("ROLLBACK")
            return {"error": "NOT_FOUND", "message": f"Taslak bulunamadı: {req_id}"}

        req = dict(row)
        expected_token = compute_approval_token(req_id, req["data_snapshot_hash"])
        if approval_token != expected_token:
            conn.execute("ROLLBACK")
            return {
                "error": "INVALID_APPROVAL_TOKEN",
                "message": "Geçersiz veya güncel olmayan taslak sürümüne ait onay imzası."
            }

        if req["status"] == "SAVED":
            conn.execute("ROLLBACK")
            return {
                "error": "DUPLICATE_EXECUTION",
                "message": "Mükerrer işlem engellendi: Bu talep zaten kaydedilmiş.",
                "req_id": req_id,
                "status": "SAVED"
            }

        current_hash = _compute_data_hash(req["sku"], req["start_date"], req["end_date"], db_path=db_path)
        if current_hash != req["data_snapshot_hash"]:
            conn.execute("ROLLBACK")
            return {
                "error": "DATA_CHANGED",
                "message": "Taslak oluşturulduktan sonra stok, talep, sipariş veya tedarikçi verisi değişti. Yeniden hesaplama ve onay gerekli."
            }

        cursor = conn.execute(
            "UPDATE purchase_requisitions SET status = 'SAVED' WHERE req_id = ? AND status = 'DRAFT'",
            (req_id,)
        )
        if cursor.rowcount == 0:
            conn.execute("ROLLBACK")
            return {
                "error": "CONCURRENT_CONFLICT",
                "message": "Eşzamanlı işlem tespit edildi; kayıt yalnızca bir kez işlendi."
            }

        conn.execute("COMMIT")
        return {
            "req_id": req_id,
            "status": "SAVED",
            "message": "Satın alma talebi test ortamına kaydedildi. Fiziksel stok artırılmadı."
        }
    except sqlite3.Error as exc:
        conn.execute("ROLLBACK")
        return {"error": "DB_ERROR", "message": str(exc)}
    finally:
        conn.close()
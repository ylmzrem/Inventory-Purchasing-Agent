import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("data/erp.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    conn = get_connection(db_path)
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn.executescript(schema_sql)
    conn.commit()
    return conn


def load_scenario_data(conn: sqlite3.Connection, scenario_data: dict) -> None:
    """Katalogdaki senaryo sözlüğünü SQLite tablolarına aktarır."""
    tables = [
        "purchase_requisitions", "price_tiers", "supplier_products",
        "suppliers", "open_orders", "demand_forecast", "inventory", "products"
    ]
    for t in tables:
        conn.execute(f"DELETE FROM {t}")

    for p in scenario_data.get("products", []):
        sku = p.get("sku") or p.get("product_id")
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                sku,
                p.get("name", sku),
                p.get("unit", "adet"),
                p.get("pcs_per_unit", 1),
                p.get("safety_stock", 0),
                p.get("reorder_point", 0),
                p.get("moq", p.get("min_order_qty", 1)),
                p.get("pack_size", p.get("pack_multiple", 1)),
            ),
        )

    stock_records = scenario_data.get("stock", scenario_data.get("inventory", []))
    for inv in stock_records:
        sku = inv.get("sku") or inv.get("product_id")
        physical = inv["physical"] if "physical" in inv else inv["physical_stock"]
        allocated = inv.get("allocated", inv.get("allocated_stock", 0))
        updated_at = inv.get("snapshot_at") or inv.get("updated_at") or inv.get("as_of") or "2026-11-23T09:00:00"
        conn.execute(
            "INSERT INTO inventory VALUES (?, ?, ?, ?)",
            (sku, physical, allocated, updated_at),
        )

    for d in scenario_data.get("demand", scenario_data.get("demand_forecast", [])):
        sku = d.get("sku") or d.get("product_id")
        demand_date = d.get("date") or d.get("demand_date") or d.get("due_date")
        qty = d["qty"] if "qty" in d else d["quantity"]
        covered = int(bool(d.get("allocated", d.get("is_covered_by_allocation", 0))))
        conn.execute(
            "INSERT INTO demand_forecast (sku, demand_date, quantity, is_covered_by_allocation) VALUES (?, ?, ?, ?)",
            (sku, demand_date, qty, covered),
        )

    for idx, oo in enumerate(scenario_data.get("open_orders", []), start=1):
        sku = oo.get("sku") or oo.get("product_id")
        po_id = oo.get("po_id") or oo.get("order_id") or f"PO-{idx:04d}"
        qty = oo["qty"] if "qty" in oo else oo["quantity"]
        exp_date = oo.get("eta") or oo.get("expected_date") or oo.get("arrival_date")
        conn.execute(
            "INSERT INTO open_orders VALUES (?, ?, ?, ?, ?)",
            (po_id, sku, qty, exp_date, oo.get("status", "CONFIRMED")),
        )

    seen_suppliers = set()
    for sup in scenario_data.get("suppliers", []):
        sid = sup["supplier_id"]
        if sid not in seen_suppliers:
            conn.execute(
                "INSERT INTO suppliers VALUES (?, ?, ?, ?)",
                (
                    sid,
                    sup.get("name", sid),
                    sup.get("reliability_score", 90.0),
                    sup.get("notes", ""),
                ),
            )
            seen_suppliers.add(sid)

        sku = sup.get("sku") or sup.get("product_id")
        if sku:
            freight_fixed = sup.get("freight_fixed", sup.get("freight_cost", 0.0))
            freight_per_unit = sup.get("freight_per_unit", 0.0)
            moq = sup.get("moq", sup.get("min_order_qty", 1))
            pack = sup.get("pack_size", sup.get("pack_multiple", 1))
            cur = conn.execute(
                """
                INSERT INTO supplier_products
                (supplier_id, sku, lead_time_days, lead_time_type, min_order_qty, pack_multiple, freight_fixed, freight_per_unit, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    sku,
                    sup["lead_time_days"],
                    sup.get("lead_time_type", "calendar"),
                    moq,
                    pack,
                    freight_fixed,
                    freight_per_unit,
                    sup.get("currency", "TRY"),
                ),
            )
            sp_id = cur.lastrowid
            base_price = sup.get("unit_price", 0.0)
            tiers = [{"min_qty": 1, "max_qty": None, "unit_price": base_price}]
            for brk in sup.get("price_breaks") or sup.get("price_tiers") or []:
                tiers.append({
                    "min_qty": brk["min_qty"],
                    "max_qty": brk.get("max_qty"),
                    "unit_price": brk["unit_price"],
                })
            for tier in tiers:
                conn.execute(
                    "INSERT INTO price_tiers (supplier_product_id, min_qty, max_qty, unit_price) VALUES (?, ?, ?, ?)",
                    (sp_id, tier["min_qty"], tier.get("max_qty"), tier["unit_price"]),
                )

    conn.commit()
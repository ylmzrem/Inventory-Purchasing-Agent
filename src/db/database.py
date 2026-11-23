import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path("data/erp.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    if str(db_path) != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
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
    """Eren'in catalog.py içindeki senaryo veri setlerini SQLite tablolarına aktarır."""
    tables = [
        "purchase_requisitions", "price_tiers", "supplier_products",
        "suppliers", "open_orders", "demand_forecast", "inventory", "products"
    ]
    for t in tables:
        conn.execute(f"DELETE FROM {t}")

    for p in scenario_data.get("products", []):
        conn.execute(
            "INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                p["product_id"],
                p.get("name", p["product_id"]),
                p.get("unit", "adet"),
                p.get("safety_stock", 0),
                p.get("reorder_point", 0),
                p.get("min_order_qty", 1),
                p.get("pack_multiple", 1),
            ),
        )

    for inv in scenario_data.get("inventory", []):
        conn.execute(
            "INSERT INTO inventory VALUES (?, ?, ?, ?)",
            (
                inv["product_id"],
                inv["physical_stock"],
                inv.get("allocated_stock", 0),
                inv.get("updated_at", "2026-11-23T09:00:00"),
            ),
        )

    for d in scenario_data.get("demand", scenario_data.get("demand_forecast", [])):
        conn.execute(
            "INSERT INTO demand_forecast (product_id, demand_date, quantity, is_covered_by_allocation) VALUES (?, ?, ?, ?)",
            (
                d["product_id"],
                d.get("date", d.get("demand_date")),
                d["quantity"],
                int(d.get("is_covered_by_allocation", 0)),
            ),
        )

    for oo in scenario_data.get("open_orders", []):
        conn.execute(
            "INSERT INTO open_orders VALUES (?, ?, ?, ?, ?)",
            (
                oo["po_id"],
                oo["product_id"],
                oo["quantity"],
                oo["expected_date"],
                oo.get("status", "CONFIRMED"),
            ),
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

        if "product_id" in sup:
            cur = conn.execute(
                """
                INSERT INTO supplier_products
                (supplier_id, product_id, lead_time_days, min_order_qty, pack_multiple, freight_cost, currency)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sid,
                    sup["product_id"],
                    sup["lead_time_days"],
                    sup.get("min_order_qty", 1),
                    sup.get("pack_multiple", 1),
                    sup.get("freight_cost", 0.0),
                    sup.get("currency", "TRY"),
                ),
            )
            sp_id = cur.lastrowid
            tiers = sup.get("price_tiers") or [{"min_qty": 1, "max_qty": None, "unit_price": sup.get("unit_price", 0.0)}]
            for tier in tiers:
                conn.execute(
                    "INSERT INTO price_tiers (supplier_product_id, min_qty, max_qty, unit_price) VALUES (?, ?, ?, ?)",
                    (sp_id, tier["min_qty"], tier.get("max_qty"), tier["unit_price"]),
                )

    conn.commit()
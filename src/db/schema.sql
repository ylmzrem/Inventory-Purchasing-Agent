CREATE TABLE IF NOT EXISTS products (
    product_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    unit TEXT NOT NULL,
    safety_stock REAL NOT NULL,
    reorder_point REAL NOT NULL,
    min_order_qty REAL NOT NULL DEFAULT 1,
    pack_multiple REAL NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS inventory (
    product_id TEXT PRIMARY KEY,
    physical_stock REAL NOT NULL,
    allocated_stock REAL NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS demand_forecast (
    demand_id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT NOT NULL,
    demand_date TEXT NOT NULL,
    quantity REAL NOT NULL,
    is_covered_by_allocation INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS open_orders (
    po_id TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    quantity REAL NOT NULL,
    expected_date TEXT NOT NULL,
    status TEXT NOT NULL, -- CONFIRMED, IN_TRANSIT, DELAYED
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    reliability_score REAL NOT NULL,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS supplier_products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    lead_time_days INTEGER NOT NULL,
    min_order_qty REAL NOT NULL DEFAULT 1,
    pack_multiple REAL NOT NULL DEFAULT 1,
    freight_cost REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'TRY',
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE IF NOT EXISTS price_tiers (
    tier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_product_id INTEGER NOT NULL,
    min_qty REAL NOT NULL,
    max_qty REAL,
    unit_price REAL NOT NULL,
    FOREIGN KEY (supplier_product_id) REFERENCES supplier_products(id)
);

CREATE TABLE IF NOT EXISTS purchase_requisitions (
    req_id TEXT PRIMARY KEY,
    idempotency_key TEXT UNIQUE,
    product_id TEXT NOT NULL,
    supplier_id TEXT NOT NULL,
    quantity REAL NOT NULL,
    total_cost REAL NOT NULL,
    currency TEXT NOT NULL,
    required_date TEXT NOT NULL,
    expected_delivery_date TEXT NOT NULL,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL, -- DRAFT, APPROVED, SAVED, REJECTED
    data_snapshot_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
from concurrent.futures import ThreadPoolExecutor
import pytest
from data.seed_data import seed_database
from src.db.database import init_db, get_connection, load_scenario_data
from src.tools.erp_tools import (
    stok_sorgula,
    talep_getir,
    satin_alma_taslagi_olustur,
    satin_alma_talebi_kaydet,
    compute_approval_token,
)
from tests.scenarios.catalog import SCENARIOS

@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_erp.db"
    seed_database(db_file)
    return db_file

def test_katalog_senaryolari_yukleme_ve_dogrulama(tmp_path):
    """Katalogdaki 24 senaryonun tamamının KeyError olmadan yüklendiğini ve ilk senaryonun stok/talep değerlerini doğrular."""
    for sc in SCENARIOS:
        db_file = tmp_path / f"{sc.id}.db"
        conn = init_db(db_file)
        load_scenario_data(conn, sc.data)
        conn.close()

    # İlk senaryo için veritabanı okuma doğrulaması
    s01 = SCENARIOS[0]
    db_s01 = tmp_path / f"{s01.id}.db"
    first_sku = s01.data["products"][0]["sku"]
    stok = stok_sorgula(first_sku, db_path=db_s01)
    assert stok["sku"] == first_sku
    assert stok["available_stock"] == stok["physical_stock"] - stok["allocated_stock"]

def test_gecersiz_stokla_taslak_durmali(test_db):
    conn = get_connection(test_db)
    conn.execute("UPDATE inventory SET allocated_stock = 999 WHERE sku = 'PRD-001'")
    conn.commit()
    conn.close()

    stok = stok_sorgula("PRD-001", db_path=test_db)
    assert stok["error"] == "INVALID_INVENTORY_RECORD"

    draft = satin_alma_taslagi_olustur(
        sku="PRD-001", supplier_id="SUP-01", quantity=50, total_cost=2400.0,
        currency="TRY", start_date="2026-11-23", end_date="2026-12-07",
        required_date="2026-11-26", expected_delivery_date="2026-11-26",
        rationale="Test", db_path=test_db
    )
    assert draft["error"] == "INVALID_INVENTORY_RECORD"

def test_onay_oncesi_talep_degisikligi_ve_token_kontrolu(test_db):
    draft = satin_alma_taslagi_olustur(
        sku="PRD-002", supplier_id="SUP-01", quantity=250, total_cost=26925.0,
        currency="TRY", start_date="2026-11-23", end_date="2026-12-07",
        required_date="2026-11-28", expected_delivery_date="2026-11-27",
        rationale="Zamanında teslimat.", db_path=test_db
    )
    req_id = draft["req_id"]
    valid_token = compute_approval_token(req_id, draft["snapshot_hash"])

    # Sahte token reddedilmeli
    bad_auth = satin_alma_talebi_kaydet(req_id, approval_token="fake-token", db_path=test_db)
    assert bad_auth["error"] == "INVALID_APPROVAL_TOKEN"

    # Onay öncesi talep sıfırlanıyor
    conn = get_connection(test_db)
    conn.execute("UPDATE demand_forecast SET quantity = 0 WHERE sku = 'PRD-002'")
    conn.commit()
    conn.close()

    res = satin_alma_talebi_kaydet(req_id, approval_token=valid_token, db_path=test_db)
    assert res["error"] == "DATA_CHANGED"

    # Veritabanında durum hâlâ DRAFT kalmış olmalı
    conn = get_connection(test_db)
    status = conn.execute("SELECT status FROM purchase_requisitions WHERE req_id = ?", (req_id,)).fetchone()["status"]
    conn.close()
    assert status == "DRAFT"

def test_eszamanli_kayit_tekil_kalmali(test_db):
    draft = satin_alma_taslagi_olustur(
        sku="PRD-001", supplier_id="SUP-01", quantity=50, total_cost=2400.0,
        currency="TRY", start_date="2026-11-23", end_date="2026-12-07",
        required_date="2026-11-26", expected_delivery_date="2026-11-26",
        rationale="Eşzamanlılık testi", db_path=test_db
    )
    req_id = draft["req_id"]
    token = compute_approval_token(req_id, draft["snapshot_hash"])

    def _call():
        return satin_alma_talebi_kaydet(req_id, approval_token=token, db_path=test_db)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: _call(), range(2)))

    succeeded = [r for r in results if "error" not in r and r.get("status") == "SAVED"]
    rejected = [r for r in results if r.get("error") in ("DUPLICATE_EXECUTION", "CONCURRENT_CONFLICT")]
    assert len(succeeded) == 1
    assert len(rejected) == 1
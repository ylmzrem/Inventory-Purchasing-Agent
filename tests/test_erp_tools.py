import pytest
from data.seed_data import seed_database
from src.db.database import get_connection
from src.tools.erp_tools import (
    stok_sorgula,
    talep_getir,
    acik_siparisler,
    tedarikci_listesi,
    satin_alma_taslagi_olustur,
    satin_alma_talebi_kaydet,
)

@pytest.fixture
def test_db(tmp_path):
    db_file = tmp_path / "test_erp.db"
    seed_database(db_file)
    return db_file

def test_stok_sorgula_kullanilabilir_stok(test_db):
    res = stok_sorgula("PRD-001", db_path=test_db)
    assert res["physical_stock"] == 400
    assert res["allocated_stock"] == 50
    assert res["available_stock"] == 350
    assert "updated_at" in res

def test_bilinmeyen_urun_hatasi(test_db):
    res = stok_sorgula("PRD-999", db_path=test_db)
    assert res["error"] == "UNKNOWN_PRODUCT"

def test_talep_getir_cift_sayim_onleme(test_db):
    res = talep_getir("PRD-002", "2026-11-23", "2026-12-07", db_path=test_db)
    assert res["total_uncovered_demand"] == 270

def test_onaysiz_ve_mukerrer_kayit_engelleme(test_db):
    draft = satin_alma_taslagi_olustur(
        product_id="PRD-002",
        supplier_id="SUP-01",
        quantity=250,
        total_cost=26550.0,
        currency="TRY",
        required_date="2026-11-28",
        expected_delivery_date="2026-11-27",
        rationale="Zamanında teslimat ve kademeli fiyat avantajı.",
        db_path=test_db
    )
    req_id = draft["req_id"]

    unapproved = satin_alma_talebi_kaydet(req_id, user_approved=False, db_path=test_db)
    assert unapproved["error"] == "APPROVAL_REQUIRED"

    saved = satin_alma_talebi_kaydet(req_id, user_approved=True, db_path=test_db)
    assert saved["status"] == "SAVED"

    duplicate = satin_alma_talebi_kaydet(req_id, user_approved=True, db_path=test_db)
    assert duplicate["error"] == "DUPLICATE_EXECUTION"

def test_onay_oncesi_veri_degisimi_kontrolu(test_db):
    draft = satin_alma_taslagi_olustur(
        product_id="PRD-003",
        supplier_id="SUP-01",
        quantity=50,
        total_cost=31200.0,
        currency="TRY",
        required_date="2026-11-27",
        expected_delivery_date="2026-11-26",
        rationale="Acil teslimat.",
        db_path=test_db
    )

    conn = get_connection(test_db)
    conn.execute("UPDATE inventory SET physical_stock = 100 WHERE product_id = 'PRD-003'")
    conn.commit()
    conn.close()

    res = satin_alma_talebi_kaydet(draft["req_id"], user_approved=True, db_path=test_db)
    assert res["error"] == "DATA_CHANGED"
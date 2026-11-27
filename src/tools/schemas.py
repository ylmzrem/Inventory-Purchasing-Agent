from src.tools.erp_tools import (
    stok_sorgula,
    talep_getir,
    acik_siparisler,
    tedarikci_listesi,
    satin_alma_taslagi_olustur,
    satin_alma_talebi_kaydet,
)

ERP_TOOLS_MAP = {
    "stok_sorgula": stok_sorgula,
    "talep_getir": talep_getir,
    "acik_siparisler": acik_siparisler,
    "tedarikci_listesi": tedarikci_listesi,
    "satin_alma_taslagi_olustur": satin_alma_taslagi_olustur,
    "satin_alma_talebi_kaydet": satin_alma_talebi_kaydet,
}

ERP_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "stok_sorgula",
            "description": "Bir ürünün fiziksel stok, ayrılmış/bloke stok, kullanılabilir stok, emniyet stoku ve sipariş kurallarını zaman damgasıyla getirir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string", "description": "Ürün kodu (SKU), örn: PRD-001"}
                },
                "required": ["sku"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "talep_getir",
            "description": "Belirli bir ürün için başlangıç ve bitiş tarihleri arasındaki tarihli talepleri getirir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD"}
                },
                "required": ["sku", "start_date", "end_date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "acik_siparisler",
            "description": "Ürüne ait verilmiş ve depoya gelmesi beklenen açık satın alma siparişlerini listeler.",
            "parameters": {
                "type": "object",
                "properties": {"sku": {"type": "string"}},
                "required": ["sku"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tedarikci_listesi",
            "description": "Ürünü sağlayabilen tedarikçileri, teslim sürelerini, nakliye ücretlerini ve kademeli birim fiyatlarını getirir.",
            "parameters": {
                "type": "object",
                "properties": {"sku": {"type": "string"}},
                "required": ["sku"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "satin_alma_taslagi_olustur",
            "description": "Kullanıcı onayına sunulmak üzere DRAFT durumunda satın alma talebi taslağı oluşturur.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sku": {"type": "string"},
                    "supplier_id": {"type": "string"},
                    "quantity": {"type": "number"},
                    "total_cost": {"type": "number"},
                    "currency": {"type": "string"},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "required_date": {"type": "string"},
                    "expected_delivery_date": {"type": "string"},
                    "rationale": {"type": "string"}
                },
                "required": [
                    "sku", "supplier_id", "quantity", "total_cost", "currency",
                    "start_date", "end_date", "required_date", "expected_delivery_date", "rationale"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "satin_alma_talebi_kaydet",
            "description": "Yalnızca uygulama arayüzünden doğrulanmış kullanıcı onay imzası (approval_token) sağlandığında taslağı SAVED olarak kaydeder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "req_id": {"type": "string"},
                    "approval_token": {"type": "string", "description": "Uygulama katmanından gelen kullanıcı onay imzası"}
                },
                "required": ["req_id", "approval_token"]
            }
        }
    }
]
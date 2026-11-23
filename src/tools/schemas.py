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
            "description": "Bir ürünün fiziksel stok, ayrılmış/bloke stok, kullanılabilir stok, emniyet stoku, minimum sipariş miktarı ve paket katı bilgilerini zaman damgasıyla getirir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string", "description": "Ürün kodu, örn: PRD-001"}
                },
                "required": ["product_id"]
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
                    "product_id": {"type": "string"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD formatında başlangıç tarihi"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD formatında bitiş tarihi"}
                },
                "required": ["product_id", "start_date", "end_date"]
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
                "properties": {
                    "product_id": {"type": "string"}
                },
                "required": ["product_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "tedarikci_listesi",
            "description": "Ürünü sağlayabilen tedarikçileri, teslim sürelerini (lead time), minimum sipariş koşullarını, nakliye ücretlerini ve kademeli birim fiyatlarını getirir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "string"}
                },
                "required": ["product_id"]
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
                    "product_id": {"type": "string"},
                    "supplier_id": {"type": "string"},
                    "quantity": {"type": "number"},
                    "total_cost": {"type": "number"},
                    "currency": {"type": "string"},
                    "required_date": {"type": "string"},
                    "expected_delivery_date": {"type": "string"},
                    "rationale": {"type": "string"}
                },
                "required": [
                    "product_id", "supplier_id", "quantity", "total_cost",
                    "currency", "required_date", "expected_delivery_date", "rationale"
                ]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "satin_alma_talebi_kaydet",
            "description": "Kullanıcı açıkça onay verdikten sonra taslak satın alma talebini test ortamına SAVED olarak kaydeder.",
            "parameters": {
                "type": "object",
                "properties": {
                    "req_id": {"type": "string"},
                    "user_approved": {"type": "boolean"}
                },
                "required": ["req_id", "user_approved"]
            }
        }
    }
]
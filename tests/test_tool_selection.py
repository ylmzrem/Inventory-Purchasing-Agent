import os
import json
import pytest
from openai import OpenAI
from src.tools.schemas import ERP_TOOL_SCHEMAS

TEST_CASES = [
    ("Depoda şu an kaç tane PRD-001 var ve ne kadarı bloke?", "stok_sorgula", {"product_id": "PRD-001"}),
    ("2026-11-23 ile 2026-12-07 arasında PRD-002 için ne kadar talep var?", "talep_getir", {"product_id": "PRD-002"}),
    ("PRD-003 için yolda olan açık siparişlerimiz hangileri?", "acik_siparisler", {"product_id": "PRD-003"}),
    ("PRD-002 ürününü hangi tedarikçilerden kaça alabiliriz?", "tedarikci_listesi", {"product_id": "PRD-002"}),
]

@pytest.mark.skipif(not os.getenv("OPENAI_API_KEY"), reason="OPENAI_API_KEY tanımlı değil")
@pytest.mark.parametrize("prompt,expected_tool,expected_args", TEST_CASES)
def test_llm_tool_selection(prompt, expected_tool, expected_args):
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Kullanıcının sorusunu yanıtlamak için yalnızca en uygun tek aracı çağır."},
            {"role": "user", "content": prompt}
        ],
        tools=ERP_TOOL_SCHEMAS,
        tool_choice="required",
        temperature=0.0
    )
    tool_call = response.choices[0].message.tool_calls[0]
    assert tool_call.function.name == expected_tool
    args = json.loads(tool_call.function.arguments)
    for k, v in expected_args.items():
        assert args.get(k) == v
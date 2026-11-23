"""GEÇİCİ test arayüzü (Streamlit) — asıl demo arayüzü (app.py) DEĞİLDİR.

Amaç: senaryo kataloğunu incelemek, değerlendirme koşucusunu çalıştırmak ve
agent entegrasyonunu tek senaryo üzerinde denemek. Asıl demo arayüzü hazır
olduğunda bu dosya kaldırılacaktır.

Çalıştırma (repo kökünden):
    pip install -r requirements-dev.txt
    streamlit run tests/dev_ui.py
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.eval import reference_calc  # noqa: E402
from tests.eval.metrics import aggregate, by_category, score  # noqa: E402
from tests.eval.schema import Scenario  # noqa: E402
from tests.eval.systems import AgentSystem, SystemUnavailable  # noqa: E402
from tests.run_evaluation import run  # noqa: E402
from tests.scenarios.catalog import SCENARIOS  # noqa: E402

st.set_page_config(page_title="Geçici Test Arayüzü", page_icon="🧪", layout="wide")
st.warning("🧪 **Geçici test arayüzü.** Sadece geliştirme ve test içindir; asıl demo arayüzü değildir.")


# --------------------------------------------------------------------------- yardımcılar

def scenario_label(s: Scenario) -> str:
    return f"{s.id} · {s.title}"


def show_table(title: str, rows: list[dict]) -> None:
    st.markdown(f"**{title}**")
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True)
    else:
        st.caption("— kayıt yok —")


class MockAgent:
    """Agent henüz yokken arayüzü denemek için sahte agent.

    Hesabı referans hesaplayıcıyla yapar; onay, kayıt, soru sorma ve uyarı
    davranışı YOKTUR. Bu yüzden onay/güvenlik senaryolarında başarısız olması normaldir.
    """

    def __init__(self, scenario: Scenario):
        self.scenario = scenario

    def __call__(self, data: dict, as_of: str) -> "MockAgent":
        self.data, self.as_of = data, as_of
        return self

    def send(self, message: str) -> str:
        if self.scenario.request is None:
            return "(sahte agent) Bu istek yapılandırılmış bir hesaba çevrilemiyor."
        out = reference_calc.compute(self.data, self.scenario.request, self.as_of)
        self._out = out
        calc = out["calc"]
        if out["outcome"] == "requisition_draft":
            return (f"(sahte agent) Taslak: {calc['supplier_id']} · {calc['order_quantity']} adet · "
                    f"{calc['total_cost_try']:,.2f} TL · teslim {calc['delivery_date']}")
        return f"(sahte agent) Sonuç: {out['outcome']} · net ihtiyaç {calc.get('net_requirement')}"

    def get_state(self) -> dict:
        out = getattr(self, "_out", None)
        if out is None:
            return {"outcome": None}
        return {"outcome": out["outcome"], "draft": out["calc"], "requisitions": [],
                "usage": {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0}, "tool_calls": ["reference_calc"]}


# --------------------------------------------------------------------------- sekmeler

tab_scenarios, tab_eval, tab_agent = st.tabs(["📋 Senaryolar", "📈 Değerlendirme", "🤖 Agent denemesi"])

with tab_scenarios:
    categories = sorted({s.category for s in SCENARIOS})
    left, right = st.columns([1, 3])
    with left:
        chosen_cats = st.multiselect("Kategori", categories, default=categories)
        pool = [s for s in SCENARIOS if s.category in chosen_cats] or SCENARIOS
        s = st.radio("Senaryo", pool, format_func=scenario_label, key="scenario_pick")
    with right:
        st.subheader(scenario_label(s))
        st.caption(f"Kategori: `{s.category}` · as_of: {s.as_of} · baseline: "
                   f"{'evet' if s.baseline_applicable else 'hayır'} · güvenlik senaryosu: "
                   f"{'evet' if s.safety_relevant else 'hayır'}")
        st.write(s.description)

        st.markdown("**Kullanıcı turları**")
        for i, turn in enumerate(s.turns, 1):
            st.markdown(f"{i}. {turn.user}")
            for patch in turn.data_patches:
                st.caption(f"↳ bu turdan önce veri değişir: {patch}")

        e = s.expected
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Beklenen sonuç**")
            st.json({"outcome": e.outcome, **e.calc, "requisitions_logged": e.requisitions_logged,
                     "clarify_topics": e.clarify_topics, "warnings": e.warnings,
                     "must_not_select": e.must_not_select, "requires_reapproval": e.requires_reapproval})
        with c2:
            st.markdown("**El hesabı**")
            for step in s.derivation:
                st.markdown(f"- {step}")

        if s.request:
            st.markdown("---")
            st.markdown(f"**Referans hesaplayıcı** — istek: `{s.request}`")
            data = s.final_data()
            proj = reference_calc.project(data, s.request["sku"], reference_calc._d(s.as_of),
                                          reference_calc._d(s.request["horizon_end"]))
            out = reference_calc.compute(data, s.request, s.as_of)
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Kullanılabilir stok", proj["available_stock"])
            m2.metric("Emniyet stoku", proj["safety_stock"])
            m3.metric("Net ihtiyaç", proj["net_requirement"])
            m4.metric("İhtiyaç tarihi", out["calc"]["need_date"] or "—")
            timeline = [{"tarih": d, "bakiye": b,
                         "durum": "⚠️ emniyet stoku altında" if b < proj["safety_stock"] else ""}
                        for d, b in proj["timeline"]]
            with st.expander("Günlük stok projeksiyonu", expanded=False):
                st.dataframe(pd.DataFrame(timeline), hide_index=True)
            show_table("Tedarikçi değerlendirmesi", out.get("evaluations", []))

        st.markdown("---")
        st.markdown("**Senaryo verisi**")
        for table in ("products", "stock", "demand", "open_orders", "suppliers"):
            with st.expander(table, expanded=table in ("stock", "suppliers")):
                show_table(table, s.data[table])
        st.caption(f"Kurlar: {s.data['fx_rates']}")


with tab_eval:
    st.markdown("Seçilen sistemleri senaryolar üzerinde çalıştırır. Raporlar `tests/results/` altına yazılır.")
    systems = st.multiselect("Sistemler", ["reference", "baseline", "agent"], default=["reference"])
    ids = st.multiselect("Senaryolar (boş = hepsi)", [x.id for x in SCENARIOS])
    if st.button("Değerlendirmeyi çalıştır", type="primary", disabled=not systems):
        with st.spinner("Çalışıyor..."):
            result = run(systems, ids or None)
        st.session_state["eval_result"] = result

    result = st.session_state.get("eval_result")
    if result:
        for name, reason in result["skipped"].items():
            st.info(f"`{name}` atlandı: {reason}")
        scores = result["scores"]
        if scores:
            st.markdown("**Özet**")
            st.dataframe(pd.DataFrame([aggregate(v) for v in scores.values() if v]), hide_index=True)
            cat_rows = {}
            for system, v in scores.items():
                for cat, val in by_category(v).items():
                    cat_rows.setdefault(cat, {"kategori": cat})[system] = val["task_success_%"]
            show_table("Kategoriye göre görev başarısı (%)", list(cat_rows.values()))
            rows = [{"sistem": x.system, "senaryo": x.scenario_id, "başarı": "✅" if x.task_success else "❌",
                     "hesap": f"{x.calc_correct}/{x.calc_checked}", "güvenli": "✅" if x.safety_ok else "❌",
                     "süre_sn": x.latency_s, "hatalar": "; ".join(x.failures)}
                    for v in scores.values() for x in v]
            show_table("Senaryo bazında", rows)
            st.caption(f"Rapor: {result['paths']['markdown']}")


with tab_agent:
    st.markdown("Tek bir senaryoyu agent adaptörü üzerinden çalıştırır: turlar sırayla gönderilir, "
                "aradaki veri değişiklikleri uygulanır ve sonuç puanlanır.")
    try:
        real_adapter = AgentSystem()
        agent_note = "Gerçek agent (`src.agent.create_agent`) bulundu."
    except SystemUnavailable as exc:
        real_adapter = None
        agent_note = f"Gerçek agent henüz yok ({exc})."
    st.caption(agent_note)

    mode = st.radio("Agent", ["Sahte agent (referans hesaplayıcı)", "Gerçek agent"],
                    index=0 if real_adapter is None else 1, horizontal=True)
    if mode == "Sahte agent (referans hesaplayıcı)":
        st.caption("Sahte agentta onay, kayıt, soru sorma ve uyarı davranışı yoktur; "
                   "bu senaryolarda başarısız olması beklenir.")
    s = st.selectbox("Senaryo", SCENARIOS, format_func=scenario_label, key="agent_pick")

    if st.button("Senaryoyu çalıştır", type="primary"):
        if mode == "Gerçek agent":
            if real_adapter is None:
                st.error("Gerçek agent bulunamadı.")
                st.stop()
            adapter = real_adapter
        else:
            adapter = AgentSystem.__new__(AgentSystem)
            adapter._create = MockAgent(s)
        r = adapter.run(s)
        sc = score(s, r)

        for msg in r.transcript:
            role = {"user": "user", "assistant": "assistant"}.get(msg["role"], "assistant")
            with st.chat_message(role):
                st.write(msg["content"])

        (st.success if sc.task_success else st.error)(
            f"Görev başarısı: {'✅' if sc.task_success else '❌'} · hesap {sc.calc_correct}/{sc.calc_checked} · "
            f"güvenli: {'✅' if sc.safety_ok else '❌'} · {r.latency_s} sn")
        for f in sc.failures:
            st.markdown(f"- {f}")
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Agent çıktısı (normalize)**")
            st.json({k: v for k, v in asdict(r).items() if k != "transcript"})
        with c2:
            st.markdown("**Beklenen**")
            st.json(asdict(s.expected))

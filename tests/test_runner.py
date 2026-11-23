"""End-to-end checks of the evaluation runner and the agent adapter (no LLM calls)."""

import json

from tests.eval.metrics import score
from tests.eval.systems import AgentSystem
from tests.run_evaluation import run
from tests.scenarios.catalog import get


def test_reference_system_scores_100_percent(tmp_path):
    result = run(["reference"], out_root=tmp_path, timestamp="t")
    scores = result["scores"]["reference"]
    assert scores and all(x.task_success for x in scores), [x.failures for x in scores if not x.task_success]
    summary = (tmp_path / "t" / "summary.md").read_text(encoding="utf-8")
    assert "task_success_%" in summary
    assert json.loads((tmp_path / "t" / "runs.json").read_text(encoding="utf-8"))["summary"][0]["task_success_%"] == 100.0


def test_missing_systems_are_skipped_not_crashed(tmp_path):
    result = run(["agent", "baseline"], ["S01"], out_root=tmp_path, timestamp="t")
    # src/agent and src/baseline do not exist yet on this branch
    assert set(result["skipped"]) <= {"agent", "baseline"}


class FakeAgent:
    """Minimal agent honouring the integration contract; reads prices at call time."""

    def __init__(self, data, as_of):
        self.data, self.as_of, self.turns = data, as_of, 0

    def send(self, message):
        self.turns += 1
        return "ok"

    def get_state(self):
        price = next(s for s in self.data["suppliers"] if s["supplier_id"] == "SUP-A")["unit_price"]
        cost = 150 * price + 350
        return {"outcome": "requisition_draft",
                "draft": {"available_stock": 120, "net_requirement": 150, "need_date": "2026-12-21",
                          "supplier_id": "SUP-A", "order_quantity": 150, "total_cost_try": cost,
                          "delivery_date": "2026-12-08"},
                "clarify_topics": [], "warnings": ["data_changed"], "requisitions": [],
                "awaiting_reapproval": True, "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.001},
                "tool_calls": ["get_stock", "compare_suppliers"]}


def test_agent_adapter_applies_data_patches_between_turns():
    adapter = AgentSystem.__new__(AgentSystem)  # bypass import of src.agent
    adapter._create = FakeAgent
    s = get("S20")  # SUP-A price rises to 44.00 before the approval turn
    r = adapter.run(s)
    assert r.error is None and r.calc["total_cost_try"] == 6950.0
    assert len(r.transcript) == 4 and r.input_tokens == 100
    assert score(s, r).task_success
    assert s.data["suppliers"][0]["unit_price"] == 42.50  # catalogue data untouched


def test_agent_adapter_records_crash_as_error():
    adapter = AgentSystem.__new__(AgentSystem)

    def boom(data, as_of):
        raise RuntimeError("LLM timeout")

    adapter._create = boom
    r = adapter.run(get("S01"))
    assert r.error == "RuntimeError: LLM timeout"
    assert not score(get("S01"), r).task_success

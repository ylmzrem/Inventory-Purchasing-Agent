"""Adapters that run a system under test on a scenario and return a RunResult.

The agent and the baseline are developed in src/ by other team members. The
adapters below only depend on the small integration contracts documented in
docs/evaluation_plan.md ("Integration contracts"). If a module is not available
yet, the adapter raises SystemUnavailable and the runner skips it.
"""

from __future__ import annotations

import copy
import importlib
import time
import traceback
from typing import Any, Protocol

from . import reference_calc
from .schema import CALC_FIELDS, RunResult, Scenario, apply_patch


class SystemUnavailable(RuntimeError):
    pass


class System(Protocol):
    name: str

    def applies_to(self, scenario: Scenario) -> bool: ...

    def run(self, scenario: Scenario) -> RunResult: ...


def _calc_subset(values: dict[str, Any] | None) -> dict[str, Any]:
    return {k: values[k] for k in CALC_FIELDS if values and k in values}


class ReferenceSystem:
    """Runs the independent reference calculator. Used to self-test the runner:
    it must score 100% on every scenario that has a structured request and only
    involves calculation (no approval / safety behaviour)."""

    name = "reference"

    def applies_to(self, scenario: Scenario) -> bool:
        return scenario.baseline_applicable

    def run(self, scenario: Scenario) -> RunResult:
        start = time.perf_counter()
        out = reference_calc.compute(scenario.final_data(), scenario.request, scenario.as_of)
        return RunResult(scenario.id, self.name, outcome=out["outcome"], calc=_calc_subset(out["calc"]),
                         latency_s=round(time.perf_counter() - start, 4))


class BaselineSystem:
    """Rule-based, non-LLM baseline.

    Contract: src/baseline.py exposes
        run_baseline(data: dict, request: dict, as_of: str) -> {"outcome": str, "calc": {...}}
    It only receives structured requests, so it runs on calculation scenarios only.
    """

    name = "baseline"

    def __init__(self) -> None:
        try:
            self._fn = importlib.import_module("src.baseline").run_baseline
        except (ImportError, AttributeError) as exc:
            raise SystemUnavailable(f"src.baseline.run_baseline not available ({exc})") from exc

    def applies_to(self, scenario: Scenario) -> bool:
        return scenario.baseline_applicable

    def run(self, scenario: Scenario) -> RunResult:
        result = RunResult(scenario.id, self.name)
        start = time.perf_counter()
        try:
            out = self._fn(copy.deepcopy(scenario.data), dict(scenario.request), scenario.as_of)
            result.outcome = out.get("outcome")
            result.calc = _calc_subset(out.get("calc"))
        except Exception as exc:  # noqa: BLE001 - any crash is a scored failure
            result.error = f"{type(exc).__name__}: {exc}"
        result.latency_s = round(time.perf_counter() - start, 4)
        return result


class AgentSystem:
    """LLM agent.

    Contract: src/agent exposes create_agent(data: dict, as_of: str) returning an object with
        send(message: str) -> str          # assistant reply for one user turn
        get_state() -> dict                # structured state after the last turn:
            {"outcome", "draft": {calc fields} | None, "clarify_topics": [...], "warnings": [...],
             "requisitions": [{"supplier_id", ...}], "awaiting_reapproval": bool,
             "usage": {"input_tokens", "output_tokens", "cost_usd"}, "tool_calls": [str]}
    The agent must read data through its tools at call time, because the harness
    mutates `data` in place between turns to simulate data changes.
    """

    name = "agent"

    def __init__(self) -> None:
        try:
            self._create = importlib.import_module("src.agent").create_agent
        except (ImportError, AttributeError) as exc:
            raise SystemUnavailable(f"src.agent.create_agent not available ({exc})") from exc

    def applies_to(self, scenario: Scenario) -> bool:
        return True

    def run(self, scenario: Scenario) -> RunResult:
        result = RunResult(scenario.id, self.name)
        data = copy.deepcopy(scenario.data)
        start = time.perf_counter()
        try:
            agent = self._create(data=data, as_of=scenario.as_of)
            for turn in scenario.turns:
                for patch in turn.data_patches:
                    apply_patch(data, patch)
                reply = agent.send(turn.user)
                result.transcript += [{"role": "user", "content": turn.user},
                                      {"role": "assistant", "content": reply}]
            state = agent.get_state() or {}
            usage = state.get("usage") or {}
            requisitions = state.get("requisitions") or []
            result.outcome = state.get("outcome")
            result.calc = _calc_subset(state.get("draft"))
            result.clarify_topics = list(state.get("clarify_topics") or [])
            result.warnings = list(state.get("warnings") or [])
            result.requisitions_logged = len(requisitions)
            result.logged_supplier_ids = [r.get("supplier_id") for r in requisitions if r.get("supplier_id")]
            result.asked_reapproval = bool(state.get("awaiting_reapproval"))
            result.input_tokens = int(usage.get("input_tokens", 0))
            result.output_tokens = int(usage.get("output_tokens", 0))
            result.cost_usd = float(usage.get("cost_usd", 0.0))
            result.tool_calls = list(state.get("tool_calls") or [])
        except Exception as exc:  # noqa: BLE001
            result.error = f"{type(exc).__name__}: {exc}"
            result.transcript.append({"role": "error", "content": traceback.format_exc(limit=3)})
        result.latency_s = round(time.perf_counter() - start, 4)
        return result


REGISTRY = {"reference": ReferenceSystem, "baseline": BaselineSystem, "agent": AgentSystem}

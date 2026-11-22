"""Shared data structures for the evaluation suite.

A *scenario* is a self-contained test case: a small dataset, the user turns sent
to the agent, an optional structured request (for the rule-based baseline and the
reference calculator) and the hand-verified expected result.

A *run result* is what a system under test (agent, baseline, reference) produced
for a scenario, normalised to the same vocabulary as the expectation.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

# Allowed final outcomes of a request.
OUTCOMES = {
    "no_order",              # stock + open orders cover demand and safety stock
    "requisition_draft",     # a purchase requisition was drafted (logged or not)
    "no_eligible_supplier",  # need exists but no supplier meets date / budget / quantity rules
    "clarification",         # critical information missing or ambiguous -> ask the user
    "not_found",             # requested product does not exist
}

# Calculation fields that can be checked against ground truth.
CALC_FIELDS = (
    "available_stock",
    "net_requirement",
    "need_date",
    "supplier_id",
    "order_quantity",
    "total_cost_try",
    "delivery_date",
)

CLARIFY_TOPICS = {"product", "quantity", "unit", "date", "budget"}
WARNINGS = {"stale_data", "data_changed"}

# Categories whose main purpose is safe behaviour rather than arithmetic.
SAFETY_CATEGORIES = {"clarification", "approval", "stale_data", "idempotency", "prompt_injection", "budget"}

CATEGORIES = {
    "no_order", "net_requirement", "projection", "allocation", "open_orders", "supplier_eligibility",
    "currency_freight", "lead_time", "pricing", *SAFETY_CATEGORIES, "context",
}


@dataclass
class Expected:
    outcome: str
    calc: dict[str, Any] = field(default_factory=dict)
    requisitions_logged: int = 0
    clarify_topics: list[str] = field(default_factory=list)
    must_not_select: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requires_reapproval: bool = False


@dataclass
class Turn:
    user: str
    # Applied to the dataset *before* this turn is sent (simulates data changing
    # between draft and approval). Each patch: {"table", "match": {...}, "set": {...}}
    data_patches: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Scenario:
    id: str
    title: str
    category: str
    description: str
    as_of: str
    data: dict[str, Any]
    turns: list[Turn]
    expected: Expected
    # Structured interpretation of the final request state:
    #   {"sku", "horizon_end", "budget_try"?, "supplier_override"?}
    # Used by the rule-based baseline and the reference calculator. None when the
    # request cannot be computed (clarification / not found scenarios).
    request: dict[str, Any] | None = None
    baseline_applicable: bool = False
    derivation: list[str] = field(default_factory=list)  # hand calculation, step by step

    @property
    def safety_relevant(self) -> bool:
        return (
            self.category in SAFETY_CATEGORIES
            or self.expected.outcome in {"clarification", "not_found", "no_eligible_supplier"}
            or self.expected.must_not_select != []
        )

    def final_data(self) -> dict[str, Any]:
        """Dataset after all turn patches are applied (state at the end of the conversation)."""
        data = copy.deepcopy(self.data)
        for turn in self.turns:
            for patch in turn.data_patches:
                apply_patch(data, patch)
        return data


@dataclass
class RunResult:
    """Normalised output of one system on one scenario."""

    scenario_id: str
    system: str
    outcome: str | None = None
    calc: dict[str, Any] = field(default_factory=dict)
    requisitions_logged: int = 0
    logged_supplier_ids: list[str] = field(default_factory=list)
    clarify_topics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    asked_reapproval: bool = False
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    tool_calls: list[str] = field(default_factory=list)
    error: str | None = None
    transcript: list[dict[str, str]] = field(default_factory=list)


def apply_patch(data: dict[str, Any], patch: dict[str, Any]) -> int:
    """Update matching rows of data[table] in place. Returns number of rows changed."""
    rows = data[patch["table"]]
    changed = 0
    for row in rows:
        if all(row.get(k) == v for k, v in patch["match"].items()):
            row.update(patch["set"])
            changed += 1
    if changed == 0:
        raise ValueError(f"Patch matched no rows: {patch}")
    return changed


def validate_scenario(s: Scenario) -> list[str]:
    """Return a list of problems (empty list = valid)."""
    errors: list[str] = []
    e = s.expected
    if s.category not in CATEGORIES:
        errors.append(f"unknown category {s.category!r}")
    if e.outcome not in OUTCOMES:
        errors.append(f"unknown outcome {e.outcome!r}")
    if unknown := set(e.calc) - set(CALC_FIELDS):
        errors.append(f"unknown calc fields {sorted(unknown)}")
    if unknown := set(e.clarify_topics) - CLARIFY_TOPICS:
        errors.append(f"unknown clarify topics {sorted(unknown)}")
    if unknown := set(e.warnings) - WARNINGS:
        errors.append(f"unknown warnings {sorted(unknown)}")
    if not s.turns:
        errors.append("no turns")
    if e.outcome == "clarification" and not e.clarify_topics:
        errors.append("clarification outcome needs clarify_topics")
    if e.outcome in {"clarification", "not_found"} and e.requisitions_logged:
        errors.append("cannot log a requisition when clarification is needed")
    if s.baseline_applicable and (s.request is None or len(s.turns) != 1):
        errors.append("baseline_applicable requires a structured request and a single turn")
    if e.outcome == "requisition_draft" and not {"supplier_id", "order_quantity", "total_cost_try"} <= set(e.calc):
        errors.append("requisition_draft must specify supplier_id, order_quantity, total_cost_try")
    if not s.derivation:
        errors.append("missing hand derivation")
    for key in ("products", "stock", "demand", "open_orders", "suppliers", "fx_rates"):
        if key not in s.data:
            errors.append(f"data missing {key!r}")
    return errors

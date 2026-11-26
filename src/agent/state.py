from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentState:
    as_of: str
    outcome: str | None = None
    draft: dict[str, Any] | None = None
    draft_version: int = 0
    clarify_topics: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    requisitions: list[dict[str, Any]] = field(default_factory=list)
    logged_draft_keys: set[str] = field(default_factory=set)
    awaiting_reapproval: bool = False
    current_sku: str | None = None
    current_horizon_end: str | None = None
    current_budget_try: float | None = None
    tool_calls: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        clean_draft = None
        if self.draft:
            clean_draft = {
                k: v
                for k, v in self.draft.items()
                if k not in {"fingerprint", "draft_version", "budget_try", "horizon_end"}
            }
        clean_reqs = [
            {k: v for k, v in r.items() if not k.startswith("_")}
            for r in self.requisitions
        ]
        return {
            "outcome": self.outcome,
            "draft": clean_draft,
            "clarify_topics": list(self.clarify_topics),
            "warnings": list(self.warnings),
            "requisitions": clean_reqs,
            "awaiting_reapproval": bool(self.awaiting_reapproval),
            "usage": {
                "input_tokens": int(self.input_tokens),
                "output_tokens": int(self.output_tokens),
                "cost_usd": round(float(self.cost_usd), 6),
            },
            "tool_calls": list(self.tool_calls),
        }

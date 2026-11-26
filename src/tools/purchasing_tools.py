from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def _parse_date(value: str | date) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _parse_datetime(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return datetime.fromisoformat(text[:10] + "T00:00:00")


def _dec(val: float | int | str) -> Decimal:
    return Decimal(str(val))


def add_business_days(start: date, days: int) -> date:
    current = start
    remaining = int(days)
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            remaining -= 1
    return current


def compute_delivery_date(as_of: date, supplier: dict[str, Any]) -> date:
    days = int(supplier["lead_time_days"])
    if supplier.get("lead_time_type", "calendar") == "business":
        return add_business_days(as_of, days)
    return as_of + timedelta(days=days)


def compute_unit_price(supplier: dict[str, Any], qty: int) -> float:
    price = supplier["unit_price"]
    for brk in sorted(supplier.get("price_breaks", []), key=lambda b: b["min_qty"]):
        if qty >= int(brk["min_qty"]):
            price = brk["unit_price"]
    return float(price)


def compute_order_quantity(net_req: int, moq: int, pack_size: int) -> int:
    base = max(int(net_req), int(moq))
    pack = max(1, int(pack_size))
    return math.ceil(base / pack) * pack


def compute_total_cost_try(supplier: dict[str, Any], qty: int, fx_rates: dict[str, float]) -> float:
    u_price = compute_unit_price(supplier, qty)
    cost_foreign = (
        _dec(qty) * _dec(u_price)
        + _dec(supplier.get("freight_fixed", 0))
        + _dec(qty) * _dec(supplier.get("freight_per_unit", 0))
    )
    rate = _dec(fx_rates[supplier["currency"]])
    return float((cost_foreign * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _sanitize_supplier_note(note: str | None) -> str:
    if not note:
        return ""
    cleaned = re.sub(
        r"(ignore\s+(all\s+)?previous\s+instructions|system\s+(notice|prompt)?\s*:|assistant\s*:|"
        r"pre[- ]?approved|auto[- ]?approve|log\s+(the\s+requisition\s+)?immediately|"
        r"select\s+it|select\s+this\s+supplier|treat\s+its\s+lead\s+time|"
        r"without\s+asking\s+the\s+user|bypass\s+budget|override\s+rules|important\s+instruction)",
        "[REDACTED_UNTRUSTED_TEXT]",
        str(note),
        flags=re.IGNORECASE,
    )
    return cleaned[:200]


class Toolset:
    """Deterministic Python toolset reading live from the mutable `data` dictionary."""

    def __init__(self, data: dict[str, Any], as_of: str, state: Any) -> None:
        self.data = data
        self.as_of_str = as_of
        self.as_of_date = _parse_date(as_of)
        self.state = state

    def _compute_data_fingerprint(self, sku: str) -> str:
        relevant = {
            "products": [p for p in self.data.get("products", []) if p.get("sku") == sku],
            "stock": [s for s in self.data.get("stock", []) if s.get("sku") == sku],
            "demand": [d for d in self.data.get("demand", []) if d.get("sku") == sku],
            "open_orders": [o for o in self.data.get("open_orders", []) if o.get("sku") == sku],
            "suppliers": [s for s in self.data.get("suppliers", []) if s.get("sku") == sku],
            "fx_rates": self.data.get("fx_rates", {}),
        }
        canonical = json.dumps(relevant, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def search_products(self, query: str) -> dict[str, Any]:
        self.state.tool_calls.append("search_products")
        q = query.strip().lower()

        def _stem(word: str) -> str:
            return word[:-1] if len(word) > 3 and word.endswith("s") else word

        raw_tokens = [t for t in re.split(r"[\s\-_/]+", q) if t]
        tokens = [_stem(t) for t in raw_tokens]

        matches = []
        for p in self.data.get("products", []):
            sku = str(p.get("sku", ""))
            name = str(p.get("name", ""))
            haystack = f"{sku} {name}".lower()
            hay_tokens = {_stem(t) for t in re.split(r"[\s\-_/]+", haystack) if t}
            if (
                q == sku.lower()
                or q in haystack
                or (tokens and all(any(tok in ht or ht in tok for ht in hay_tokens) for tok in tokens))
            ):
                matches.append({
                    "sku": sku,
                    "name": name,
                    "unit": p.get("unit"),
                    "safety_stock": p.get("safety_stock"),
                    "pcs_per_unit": p.get("pcs_per_unit"),
                })

        if not matches:
            all_catalog = [
                {"sku": p.get("sku"), "name": p.get("name"), "unit": p.get("unit"), "pcs_per_unit": p.get("pcs_per_unit")}
                for p in self.data.get("products", [])
            ]
            return {
                "status": "not_found",
                "matches": [],
                "available_catalog": all_catalog,
                "message": (
                    f"No product matched '{query}'. Check `available_catalog` in case a differently phrased "
                    "product exists; if none matches the user's request, call `record_clarification(topics=['product'])` "
                    "and tell the user the product was not found."
                ),
            }

        exact = next((m for m in matches if m["sku"].lower() == q), None)
        if exact:
            return {"status": "ok", "product": exact}

        if len(matches) > 1:
            return {
                "status": "multiple_matches",
                "matches": matches,
                "message": (
                    "Multiple catalog items matched this query. If the user's message already disambiguates "
                    "which item (e.g., via model number like 6204), proceed with that exact SKU; otherwise "
                    "call `record_clarification(topics=['product'])` and ask the user which SKU they mean."
                ),
            }

        return {"status": "ok", "product": matches[0]}

        return {"status": "ok", "product": matches[0]}

    def get_inventory_and_demand(self, sku: str) -> dict[str, Any]:
        self.state.tool_calls.append("get_inventory_and_demand")
        product = next((p for p in self.data.get("products", []) if p.get("sku") == sku), None)
        if not product:
            self.state.outcome = "not_found"
            if "product" not in self.state.clarify_topics:
                self.state.clarify_topics.append("product")
            return {"status": "not_found", "error": f"Unknown SKU: {sku}"}

        stock = next((s for s in self.data.get("stock", []) if s.get("sku") == sku), None)
        if not stock or stock.get("physical") is None or stock.get("allocated") is None:
            return {"status": "invalid_data", "error": f"Missing or corrupted stock record for {sku}"}

        physical = int(stock["physical"])
        allocated = int(stock["allocated"])
        available = physical - allocated

        snapshot_raw = stock.get("snapshot_at")
        is_stale = False
        if snapshot_raw:
            snap_dt = _parse_datetime(snapshot_raw).replace(tzinfo=None)
            as_of_dt = _parse_datetime(self.as_of_str).replace(tzinfo=None)
            age_hours = (as_of_dt - snap_dt).total_seconds() / 3600.0
            if age_hours > 24.0:
                is_stale = True
                if "stale_data" not in self.state.warnings:
                    self.state.warnings.append("stale_data")

        demand_rows = [d for d in self.data.get("demand", []) if d.get("sku") == sku]
        open_orders = [o for o in self.data.get("open_orders", []) if o.get("sku") == sku]

        return {
            "status": "ok",
            "sku": sku,
            "product_name": product.get("name"),
            "unit": product.get("unit"),
            "pcs_per_unit": product.get("pcs_per_unit"),
            "safety_stock": int(product.get("safety_stock", 0)),
            "physical_stock": physical,
            "allocated_stock": allocated,
            "available_stock": available,
            "snapshot_at": snapshot_raw,
            "stale_data_warning": is_stale,
            "demand_rows": demand_rows,
            "open_orders": open_orders,
        }

    def calculate_net_requirements(self, sku: str, horizon_end: str) -> dict[str, Any]:
        self.state.tool_calls.append("calculate_net_requirements")
        product = next((p for p in self.data.get("products", []) if p.get("sku") == sku), None)
        if not product:
            self.state.outcome = "not_found"
            if "product" not in self.state.clarify_topics:
                self.state.clarify_topics.append("product")
            return {"status": "not_found", "error": f"Unknown SKU: {sku}"}

        stock = next((s for s in self.data.get("stock", []) if s.get("sku") == sku), None)
        if not stock:
            return {"status": "invalid_data", "error": f"Missing stock for {sku}"}

        h_end = _parse_date(horizon_end)
        available = int(stock["physical"]) - int(stock["allocated"])
        safety = int(product["safety_stock"])

        receipts: dict[date, int] = {}
        ignored_late_orders = []
        for po in self.data.get("open_orders", []):
            if po.get("sku") == sku:
                eta = _parse_date(po["eta"])
                if eta <= h_end:
                    eff_day = max(eta, self.as_of_date)
                    receipts[eff_day] = receipts.get(eff_day, 0) + int(po["qty"])
                else:
                    ignored_late_orders.append(po)

        demand_by_day: dict[date, int] = {}
        for row in self.data.get("demand", []):
            if row.get("sku") == sku and not row.get("allocated", False):
                d_day = _parse_date(row["date"])
                if self.as_of_date <= d_day <= h_end:
                    demand_by_day[d_day] = demand_by_day.get(d_day, 0) + int(row["qty"])

        balance = available
        need_date: date | None = None
        worst_gap = 0
        day = self.as_of_date
        while day <= h_end:
            balance += receipts.get(day, 0) - demand_by_day.get(day, 0)
            if balance < safety and need_date is None:
                need_date = day
            worst_gap = max(worst_gap, safety - balance)
            day += timedelta(days=1)

        net_req = max(0, worst_gap) if need_date is not None else 0
        self.state.current_sku = sku
        self.state.current_horizon_end = h_end.isoformat()

        if need_date is None:
            self.state.outcome = "no_order"
            self.state.draft = {
                "sku": sku,
                "available_stock": available,
                "net_requirement": 0,
                "need_date": None,
            }
            return {
                "status": "no_order",
                "sku": sku,
                "unit": product.get("unit"),
                "available_stock": available,
                "safety_stock": safety,
                "net_requirement": 0,
                "need_date": None,
                "ignored_late_orders": ignored_late_orders,
                "message": "Available stock and on-time open orders cover demand and safety stock.",
            }

        return {
            "status": "need_detected",
            "sku": sku,
            "unit": product.get("unit"),
            "available_stock": available,
            "safety_stock": safety,
            "net_requirement": net_req,
            "need_date": need_date.isoformat(),
            "ignored_late_orders": ignored_late_orders,
        }

    def compare_suppliers(
        self,
        sku: str,
        net_requirement: int,
        need_date: str,
        available_stock: int,
        budget_try: float | None = None,
        supplier_override: str | None = None,
    ) -> dict[str, Any]:
        self.state.tool_calls.append("compare_suppliers")
        need_dt = _parse_date(need_date)
        fx_rates = self.data.get("fx_rates", {})
        suppliers = [s for s in self.data.get("suppliers", []) if s.get("sku") == sku]

        if not suppliers:
            self.state.outcome = "no_eligible_supplier"
            self.state.draft = None
            return {"status": "no_eligible_supplier", "reason": "No suppliers registered for this SKU."}

        evaluations = []
        for s in suppliers:
            qty = compute_order_quantity(net_requirement, int(s["moq"]), int(s["pack_size"]))
            cost_try = compute_total_cost_try(s, qty, fx_rates)
            deliv_dt = compute_delivery_date(self.as_of_date, s)
            on_time = deliv_dt <= need_dt
            within_budget = budget_try is None or cost_try <= float(budget_try)
            eligible = on_time and within_budget

            reject_reasons = []
            if not on_time:
                reject_reasons.append(f"Late delivery ({deliv_dt.isoformat()} > need_date {need_dt.isoformat()})")
            if not within_budget:
                reject_reasons.append(f"Exceeds budget ({cost_try:.2f} TRY > {float(budget_try):.2f} TRY)")

            evaluations.append({
                "supplier_id": s["supplier_id"],
                "supplier_name": s.get("name"),
                "currency": s["currency"],
                "applied_unit_price": compute_unit_price(s, qty),
                "moq": int(s["moq"]),
                "pack_size": int(s["pack_size"]),
                "order_quantity": qty,
                "total_cost_try": cost_try,
                "delivery_date": deliv_dt.isoformat(),
                "on_time": on_time,
                "within_budget": within_budget,
                "eligible": eligible,
                "reject_reasons": reject_reasons,
                "untrusted_note_summary": _sanitize_supplier_note(s.get("note")),
            })

        candidates = [e for e in evaluations if e["eligible"]]
        if supplier_override:
            candidates = [e for e in candidates if e["supplier_id"] == supplier_override]

        if not candidates:
            self.state.outcome = "no_eligible_supplier"
            self.state.draft = {
                "sku": sku,
                "available_stock": int(available_stock),
                "net_requirement": int(net_requirement),
                "need_date": need_dt.isoformat(),
            }
            return {
                "status": "no_eligible_supplier",
                "evaluations": evaluations,
                "message": "No supplier meets delivery deadline, budget, or override constraints.",
            }

        best = min(candidates, key=lambda e: (e["total_cost_try"], e["delivery_date"], e["supplier_id"]))
        fingerprint = self._compute_data_fingerprint(sku)

        draft = {
            "sku": sku,
            "available_stock": int(available_stock),
            "net_requirement": int(net_requirement),
            "need_date": need_dt.isoformat(),
            "supplier_id": best["supplier_id"],
            "order_quantity": best["order_quantity"],
            "total_cost_try": best["total_cost_try"],
            "delivery_date": best["delivery_date"],
            "budget_try": budget_try,
            "horizon_end": self.state.current_horizon_end,
            "fingerprint": fingerprint,
        }

        self.state.draft_version += 1
        draft["draft_version"] = self.state.draft_version
        self.state.draft = draft
        self.state.outcome = "requisition_draft"
        self.state.awaiting_reapproval = False

        return {
            "status": "draft_created",
            "selected_draft": {k: v for k, v in draft.items() if k != "fingerprint"},
            "all_evaluations": evaluations,
            "message": "Draft created. Ask the user for explicit approval before logging any requisition.",
        }

    def manage_requisition(self, action: str) -> dict[str, Any]:
        self.state.tool_calls.append("manage_requisition")
        draft = self.state.draft
        if not draft:
            return {"status": "error", "message": "No active requisition draft to process."}

        if action == "reject":
            self.state.awaiting_reapproval = False
            return {"status": "rejected", "message": "Draft was not logged. Ready for revision or cancellation."}

        if action != "approve":
            return {"status": "error", "message": f"Unsupported action '{action}'. Use 'approve' or 'reject'."}

        sku = draft["sku"]
        draft_key = f"{sku}:v{draft['draft_version']}:{draft['fingerprint']}"

        if draft_key in self.state.logged_draft_keys:
            existing = next(
                (r for r in self.state.requisitions if r.get("_draft_key") == draft_key),
                self.state.requisitions[-1],
            )
            return {
                "status": "already_logged",
                "requisition_id": existing["requisition_id"],
                "message": "This draft has already been approved and logged. Duplicate record prevented.",
            }

        current_fp = self._compute_data_fingerprint(sku)
        if current_fp != draft["fingerprint"]:
            if "data_changed" not in self.state.warnings:
                self.state.warnings.append("data_changed")
            horizon_end = draft.get("horizon_end") or self.state.current_horizon_end
            req_calc = self.calculate_net_requirements(sku, horizon_end)
            if req_calc.get("status") == "need_detected":
                self.compare_suppliers(
                    sku=sku,
                    net_requirement=req_calc["net_requirement"],
                    need_date=req_calc["need_date"],
                    available_stock=req_calc["available_stock"],
                    budget_try=draft.get("budget_try"),
                )
            self.state.awaiting_reapproval = True
            return {
                "status": "data_changed_reapproval_required",
                "warnings": list(self.state.warnings),
                "updated_draft": {k: v for k, v in (self.state.draft or {}).items() if k != "fingerprint"},
                "message": (
                    "Underlying stock, demand, supplier price, or FX data changed since the draft was created. "
                    "Nothing was logged. Show the updated draft and request renewed approval."
                ),
            }

        req_id = f"REQ-{len(self.state.requisitions) + 1:04d}-{uuid.uuid4().hex[:6].upper()}"
        record = {
            "requisition_id": req_id,
            "sku": draft["sku"],
            "supplier_id": draft["supplier_id"],
            "order_quantity": draft["order_quantity"],
            "total_cost_try": draft["total_cost_try"],
            "need_date": draft["need_date"],
            "delivery_date": draft["delivery_date"],
            "status": "TEST_LOGGED",
            "_draft_key": draft_key,
        }
        self.state.requisitions.append(record)
        self.state.logged_draft_keys.add(draft_key)
        self.state.awaiting_reapproval = False

        return {
            "status": "logged",
            "requisition_id": req_id,
            "record": {k: v for k, v in record.items() if not k.startswith("_")},
            "message": "Purchase requisition logged to the test environment. Physical stock was not modified.",
        }

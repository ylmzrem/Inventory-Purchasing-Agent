"""Independent reference calculator (test oracle).

This is NOT the production calculation engine (that lives in src/tools/). It is a
small, separately written implementation of the agreed rules, used only to
cross-check the hand-calculated ground truth in the scenario catalogue. If the
production engine and this oracle disagree, one of them (or the rule) is wrong
and the difference must be resolved as a team.

Rules implemented (see docs/evaluation_plan.md, "Calculation assumptions"):
  A1  available = physical - allocated
  A2  demand rows with allocated=True are already covered by allocated stock -> excluded
  A3  daily projection from as_of to horizon_end (inclusive):
        balance(d) = available + receipts(eta <= d) - demand(date <= d)
      open orders arriving after horizon_end are ignored
  A4  need_date = first day with balance(d) < safety_stock
      net_requirement = max over horizon of (safety_stock - balance(d)), at least 0
  A5  order_quantity = ceil(max(net, moq) / pack_size) * pack_size
  A6  unit price: all-units price break (highest min_qty <= quantity)
      total_cost_try = (qty * unit_price + freight_fixed + qty * freight_per_unit) * fx_rate,
      rounded half-up to 2 decimals
  A7  delivery_date = as_of + lead time (calendar days, or business days Mon-Fri)
      eligible if delivery_date <= need_date and (no budget or total_cost_try <= budget)
  A8  choose the lowest total_cost_try; ties -> earlier delivery, then supplier_id
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any


def _d(value: str | date) -> date:
    return value if isinstance(value, date) else date.fromisoformat(value[:10])


def _dec(x: float | int) -> Decimal:
    return Decimal(str(x))


def add_business_days(start: date, days: int) -> date:
    current = start
    while days > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            days -= 1
    return current


def delivery_date(as_of: date, supplier: dict[str, Any]) -> date:
    days = int(supplier["lead_time_days"])
    if supplier.get("lead_time_type", "calendar") == "business":
        return add_business_days(as_of, days)
    return as_of + timedelta(days=days)


def unit_price(supplier: dict[str, Any], qty: int) -> float:
    price = supplier["unit_price"]
    for brk in sorted(supplier.get("price_breaks", []), key=lambda b: b["min_qty"]):
        if qty >= brk["min_qty"]:
            price = brk["unit_price"]
    return price


def order_quantity(net: int, moq: int, pack: int) -> int:
    return math.ceil(max(net, moq) / pack) * pack


def total_cost_try(supplier: dict[str, Any], qty: int, fx_rates: dict[str, float]) -> float:
    cost = (
        _dec(qty) * _dec(unit_price(supplier, qty))
        + _dec(supplier.get("freight_fixed", 0))
        + _dec(qty) * _dec(supplier.get("freight_per_unit", 0))
    )
    rate = _dec(fx_rates[supplier["currency"]])
    return float((cost * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def project(data: dict[str, Any], sku: str, as_of: date, horizon_end: date) -> dict[str, Any]:
    product = next(p for p in data["products"] if p["sku"] == sku)
    stock = next(s for s in data["stock"] if s["sku"] == sku)
    available = int(stock["physical"]) - int(stock["allocated"])
    safety = int(product["safety_stock"])

    receipts: dict[date, int] = {}
    for po in data["open_orders"]:
        if po["sku"] == sku and _d(po["eta"]) <= horizon_end:
            day = max(_d(po["eta"]), as_of)
            receipts[day] = receipts.get(day, 0) + int(po["qty"])
    demand: dict[date, int] = {}
    for row in data["demand"]:
        if row["sku"] == sku and not row.get("allocated", False) and as_of <= _d(row["date"]) <= horizon_end:
            demand[_d(row["date"])] = demand.get(_d(row["date"]), 0) + int(row["qty"])

    balance = available
    need_date = None
    worst_gap = 0
    day = as_of
    timeline = []
    while day <= horizon_end:
        balance += receipts.get(day, 0) - demand.get(day, 0)
        timeline.append((day.isoformat(), balance))
        if balance < safety and need_date is None:
            need_date = day
        worst_gap = max(worst_gap, safety - balance)
        day += timedelta(days=1)

    return {
        "available_stock": available,
        "safety_stock": safety,
        "need_date": need_date,
        "net_requirement": max(0, worst_gap) if need_date else 0,
        "timeline": timeline,
    }


def compute(data: dict[str, Any], request: dict[str, Any], as_of: str | date) -> dict[str, Any]:
    """Return the expected outcome and calc fields for a structured request."""
    as_of = _d(as_of)
    sku = request["sku"]
    if not any(p["sku"] == sku for p in data["products"]):
        return {"outcome": "not_found", "calc": {}}

    proj = project(data, sku, as_of, _d(request["horizon_end"]))
    calc: dict[str, Any] = {
        "available_stock": proj["available_stock"],
        "net_requirement": proj["net_requirement"],
        "need_date": proj["need_date"].isoformat() if proj["need_date"] else None,
    }
    if proj["need_date"] is None:
        return {"outcome": "no_order", "calc": calc, "evaluations": []}

    budget = request.get("budget_try")
    evaluations = []
    for s in data["suppliers"]:
        if s["sku"] != sku:
            continue
        qty = order_quantity(proj["net_requirement"], int(s["moq"]), int(s["pack_size"]))
        cost = total_cost_try(s, qty, data["fx_rates"])
        delivery = delivery_date(as_of, s)
        on_time = delivery <= proj["need_date"]
        within_budget = budget is None or cost <= budget
        evaluations.append({
            "supplier_id": s["supplier_id"],
            "order_quantity": qty,
            "total_cost_try": cost,
            "delivery_date": delivery.isoformat(),
            "on_time": on_time,
            "within_budget": within_budget,
            "eligible": on_time and within_budget,
        })

    candidates = [e for e in evaluations if e["eligible"]]
    if override := request.get("supplier_override"):
        candidates = [e for e in candidates if e["supplier_id"] == override]
    if not candidates:
        return {"outcome": "no_eligible_supplier", "calc": calc, "evaluations": evaluations}

    best = min(candidates, key=lambda e: (e["total_cost_try"], e["delivery_date"], e["supplier_id"]))
    calc.update({k: best[k] for k in ("supplier_id", "order_quantity", "total_cost_try", "delivery_date")})
    return {"outcome": "requisition_draft", "calc": calc, "evaluations": evaluations}

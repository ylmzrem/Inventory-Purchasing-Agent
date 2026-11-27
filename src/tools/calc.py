from __future__ import annotations

import math
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

DEFAULT_FX_RATES = {"TRY": 1.0, "USD": 35.0, "EUR": 38.0}


def _to_date(value: str | date) -> date:
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


def compute_delivery_date(as_of: str | date, lead_time_days: int, lead_time_type: str = "calendar") -> str:
    start = _to_date(as_of)
    days = int(lead_time_days)
    if lead_time_type == "business":
        return add_business_days(start, days).isoformat()
    return (start + timedelta(days=days)).isoformat()


def round_order_quantity(net_requirement: int | float, moq: int | float = 1, pack_size: int | float = 1) -> int:
    if net_requirement <= 0:
        return 0
    return int(math.ceil(max(net_requirement, moq) / pack_size) * pack_size)


def get_unit_price(supplier: dict[str, Any], qty: int) -> float:
    price = supplier.get("unit_price", 0.0)
    breaks = supplier.get("price_breaks") or supplier.get("price_tiers") or []
    for brk in sorted(breaks, key=lambda b: b["min_qty"]):
        if qty >= brk["min_qty"]:
            price = brk["unit_price"]
    return float(price)


def compute_total_cost_try(supplier: dict[str, Any], qty: int, fx_rates: dict[str, float] | None = None) -> float:
    rates = {**DEFAULT_FX_RATES, **(fx_rates or {})}
    unit_p = get_unit_price(supplier, qty)
    freight_fixed = supplier.get("freight_fixed", supplier.get("freight_cost", 0))
    freight_per_unit = supplier.get("freight_per_unit", 0)
    cost = _dec(qty) * _dec(unit_p) + _dec(freight_fixed) + _dec(qty) * _dec(freight_per_unit)
    rate = _dec(rates[supplier.get("currency", "TRY")])
    return float((cost * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def compute_daily_projection(
    available_stock: int | float,
    safety_stock: int | float,
    as_of: str | date,
    horizon_end: str | date,
    demand_items: list[dict[str, Any]],
    open_orders: list[dict[str, Any]],
) -> dict[str, Any]:
    start = _to_date(as_of)
    end = _to_date(horizon_end)
    safety = int(safety_stock)
    available = int(available_stock)

    receipts: dict[date, int] = {}
    for po in open_orders:
        if po.get("status", "CONFIRMED") not in ("CONFIRMED", "IN_TRANSIT", "DELAYED"):
            continue
        eta_val = po.get("eta") or po.get("expected_date")
        if not eta_val:
            continue
        eta_dt = _to_date(eta_val)
        if eta_dt <= end:
            day = max(eta_dt, start)
            qty = int(po["qty"] if "qty" in po else po["quantity"])
            receipts[day] = receipts.get(day, 0) + qty

    demand: dict[date, int] = {}
    for row in demand_items:
        is_alloc = row.get("allocated", row.get("is_covered_by_allocation", False))
        if is_alloc:
            continue
        dt_val = row.get("date") or row.get("demand_date")
        if not dt_val:
            continue
        dt = _to_date(dt_val)
        if start <= dt <= end:
            qty = int(row["qty"] if "qty" in row else row["quantity"])
            demand[dt] = demand.get(dt, 0) + qty

    balance = available
    need_date: date | None = None
    worst_gap = 0
    day = start
    timeline = []

    while day <= end:
        balance += receipts.get(day, 0) - demand.get(day, 0)
        timeline.append((day.isoformat(), balance))
        if balance < safety and need_date is None:
            need_date = day
        worst_gap = max(worst_gap, safety - balance)
        day += timedelta(days=1)

    return {
        "available_stock": available,
        "safety_stock": safety,
        "need_date": need_date.isoformat() if need_date else None,
        "net_requirement": max(0, worst_gap) if need_date else 0,
        "timeline": timeline,
    }


def evaluate_suppliers(
    sku: str,
    net_requirement: int,
    need_date: str | date,
    as_of: str | date,
    suppliers: list[dict[str, Any]],
    fx_rates: dict[str, float] | None = None,
    budget_try: float | None = None,
) -> list[dict[str, Any]]:
    need_dt = _to_date(need_date)
    evaluations = []

    for s in suppliers:
        if (s.get("sku") or s.get("product_id")) != sku:
            continue
        moq = int(s.get("moq", s.get("min_order_qty", 1)))
        pack = int(s.get("pack_size", s.get("pack_multiple", 1)))
        qty = round_order_quantity(net_requirement, moq, pack)
        cost = compute_total_cost_try(s, qty, fx_rates)
        delivery = compute_delivery_date(as_of, int(s["lead_time_days"]), s.get("lead_time_type", "calendar"))
        on_time = _to_date(delivery) <= need_dt
        within_budget = budget_try is None or cost <= float(budget_try)

        evaluations.append({
            "supplier_id": s["supplier_id"],
            "name": s.get("name", s["supplier_id"]),
            "order_quantity": qty,
            "total_cost_try": cost,
            "delivery_date": delivery,
            "on_time": on_time,
            "within_budget": within_budget,
            "eligible": on_time and within_budget,
        })

    return evaluations
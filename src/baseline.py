from __future__ import annotations

from datetime import date
from typing import Any
from src.tools.calc import compute_daily_projection, evaluate_suppliers


def run_baseline(data: dict[str, Any], request: dict[str, Any], as_of: str | date) -> dict[str, Any]:
    """
    Deterministik baseline: A1-A8 kurallarını kullanarak net ihtiyacı hesaplar
    ve zamanında/bütçe dahilinde teslim edebilen en düşük maliyetli tedarikçiyi seçer.
    """
    sku = request.get("sku") or request.get("product_id")
    horizon_end = request.get("horizon_end") or request.get("end_date")

    products = {(p.get("sku") or p.get("product_id")): p for p in data.get("products", [])}
    stocks = {(s.get("sku") or s.get("product_id")): s for s in data.get("stock", data.get("inventory", []))}

    if not sku or sku not in products or sku not in stocks or not horizon_end:
        return {"outcome": "not_found", "calc": {}}

    prod = products[sku]
    inv = stocks[sku]
    physical = int(inv["physical"] if "physical" in inv else inv["physical_stock"])
    allocated = int(inv.get("allocated", inv.get("allocated_stock", 0)))
    available = physical - allocated

    sku_demand = [d for d in data.get("demand", data.get("demand_forecast", [])) if (d.get("sku") or d.get("product_id")) == sku]
    sku_orders = [o for o in data.get("open_orders", []) if (o.get("sku") or o.get("product_id")) == sku]

    proj = compute_daily_projection(
        available_stock=available,
        safety_stock=int(prod.get("safety_stock", 0)),
        as_of=as_of,
        horizon_end=horizon_end,
        demand_items=sku_demand,
        open_orders=sku_orders,
    )

    calc: dict[str, Any] = {
        "available_stock": proj["available_stock"],
        "net_requirement": proj["net_requirement"],
        "need_date": proj["need_date"],
    }

    if proj["need_date"] is None:
        return {"outcome": "no_order", "calc": calc}

    evaluations = evaluate_suppliers(
        sku=sku,
        net_requirement=proj["net_requirement"],
        need_date=proj["need_date"],
        as_of=as_of,
        suppliers=data.get("suppliers", []),
        fx_rates=data.get("fx_rates"),
        budget_try=request.get("budget_try"),
    )

    candidates = [e for e in evaluations if e["eligible"]]
    if override := request.get("supplier_override"):
        candidates = [e for e in candidates if e["supplier_id"] == override]

    if not candidates:
        return {"outcome": "no_eligible_supplier", "calc": calc}

    best = min(candidates, key=lambda e: (e["total_cost_try"], e["delivery_date"], e["supplier_id"]))
    calc.update({
        "supplier_id": best["supplier_id"],
        "order_quantity": best["order_quantity"],
        "total_cost_try": best["total_cost_try"],
        "delivery_date": best["delivery_date"],
    })
    return {"outcome": "requisition_draft", "calc": calc}
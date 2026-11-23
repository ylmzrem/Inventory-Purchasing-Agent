"""Quality checks for the scenario catalogue itself.

The most important test: every hand-calculated expectation must agree with the
independent reference calculator. A failure means either the hand calculation
or the reference implementation is wrong.
"""

from collections import Counter
from datetime import date

import pytest

from tests.eval import reference_calc as ref
from tests.eval.schema import CALC_FIELDS, validate_scenario
from tests.scenarios.catalog import SCENARIOS

IDS = [s.id for s in SCENARIOS]


def test_at_least_20_scenarios_with_unique_ids():
    assert len(SCENARIOS) >= 20
    assert len(set(IDS)) == len(IDS)


def test_required_edge_cases_are_covered():
    categories = Counter(s.category for s in SCENARIOS)
    for required in ("projection", "clarification", "open_orders", "currency_freight", "approval",
                     "stale_data", "prompt_injection", "idempotency", "supplier_eligibility"):
        assert categories[required] >= 1, required


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_scenario_is_valid(scenario):
    assert validate_scenario(scenario) == []


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.request], ids=lambda s: s.id)
def test_hand_calculation_matches_reference(scenario):
    out = ref.compute(scenario.final_data(), scenario.request, scenario.as_of)
    assert out["outcome"] == scenario.expected.outcome
    for name, expected in scenario.expected.calc.items():
        assert out["calc"].get(name) == expected, f"{name}: reference {out['calc'].get(name)!r} vs hand {expected!r}"


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.expected.outcome == "requisition_draft"],
                         ids=lambda s: s.id)
def test_draft_scenarios_check_every_calc_field(scenario):
    assert set(scenario.expected.calc) == set(CALC_FIELDS)


def test_must_not_select_is_never_the_expected_supplier():
    for s in SCENARIOS:
        assert s.expected.calc.get("supplier_id") not in s.expected.must_not_select, s.id


def test_injection_scenario_contains_injection_text():
    s = next(x for x in SCENARIOS if x.category == "prompt_injection")
    assert any("Ignore all previous instructions" in sup["note"] for sup in s.data["suppliers"])


def test_patches_apply_and_do_not_mutate_original():
    s = next(x for x in SCENARIOS if any(t.data_patches for t in x.turns))
    before = [sup["unit_price"] for sup in s.data["suppliers"]]
    after = s.final_data()
    assert [sup["unit_price"] for sup in s.data["suppliers"]] == before
    assert after != s.data


class TestReferenceHelpers:
    def test_business_days_skip_weekend(self):
        assert ref.add_business_days(date(2026, 12, 1), 3) == date(2026, 12, 4)    # Tue -> Fri
        assert ref.add_business_days(date(2026, 12, 1), 4) == date(2026, 12, 7)    # skips Sat/Sun
        assert ref.add_business_days(date(2026, 12, 4), 1) == date(2026, 12, 7)    # Fri -> Mon

    @pytest.mark.parametrize("net, moq, pack, qty", [(150, 100, 50, 150), (110, 100, 50, 150), (30, 100, 50, 100),
                                                     (16, 10, 5, 20), (8, 5, 5, 10), (1, 1, 1, 1)])
    def test_order_quantity(self, net, moq, pack, qty):
        assert ref.order_quantity(net, moq, pack) == qty

    def test_price_break_and_rounding(self):
        sup = {"currency": "EUR", "unit_price": 1.005, "price_breaks": [{"min_qty": 10, "unit_price": 0.5}],
               "freight_fixed": 0}
        assert ref.total_cost_try(sup, 1, {"EUR": 1.0}) == 1.01   # half-up rounding
        assert ref.total_cost_try(sup, 10, {"EUR": 2.0}) == 10.0  # break applies to all units

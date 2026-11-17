"""Kindergeld + Basiselterngeld estimate (§ 66 EStG, § 2 BEEG)."""

import json
from datetime import date

import pytest

from expat.schemas.profile import Citizenship, ResidenceStatus
from expat.tools._common import ToolError
from expat.tools.family_benefits import (
    FamilyBenefitsInput,
    FamilyBenefitsResult,
    estimate_family_benefits,
    estimate_family_benefits_tool,
    replacement_rate,
)
from expat.tools.rules import load_rules

TODAY = date(2026, 11, 17)
BIRTH = date(2026, 6, 1)


def _ok(**kwargs: object) -> FamilyBenefitsResult:
    result = estimate_family_benefits(FamilyBenefitsInput.model_validate(kwargs), today=TODAY)
    assert isinstance(result, FamilyBenefitsResult), result
    return result


def _elterngeld(net: float, **kwargs: object) -> FamilyBenefitsResult:
    return _ok(
        children_count=1,
        include_elterngeld=True,
        child_birth_date=BIRTH,
        avg_monthly_net_income_before_birth=net,
        **kwargs,
    )


# --- Kindergeld --------------------------------------------------------------------------------------


@pytest.mark.parametrize(("children", "total"), [(0, 0), (1, 259), (2, 518), (3, 777)])
def test_kindergeld_is_259_per_child(children: int, total: float) -> None:
    result = _ok(children_count=children, residence_status=ResidenceStatus.BLUE_CARD)
    assert result.kindergeld_per_child_eur == 259
    assert result.kindergeld_monthly_total_eur == total
    assert result.elterngeld_basis_monthly_estimate_eur is None
    assert "§ 66 Abs. 1 EStG" in result.legal_basis


def test_kindergeld_before_2026_amount_is_refused() -> None:
    result = estimate_family_benefits(FamilyBenefitsInput(children_count=1, as_of=date(2025, 12, 1)))
    assert isinstance(result, ToolError)


# --- eligibility -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("citizenship", "status", "expected"),
    [
        (Citizenship.NON_EU, ResidenceStatus.BLUE_CARD, "likely"),
        (Citizenship.NON_EU, ResidenceStatus.SETTLEMENT, "likely"),
        (Citizenship.NON_EU, ResidenceStatus.FAMILY_REUNION, "check"),
        (Citizenship.NON_EU, ResidenceStatus.WORK_PERMIT, "check"),
        (Citizenship.NON_EU, ResidenceStatus.STUDENT, "unlikely"),
        (Citizenship.NON_EU, None, "check"),
        (Citizenship.EU, None, "likely"),
        (Citizenship.GERMAN, ResidenceStatus.UNKNOWN, "likely"),
    ],
)
def test_eligibility_by_residence_status(
    citizenship: Citizenship, status: ResidenceStatus | None, expected: str
) -> None:
    result = _ok(children_count=1, citizenship=citizenship, residence_status=status)
    assert result.eligible == expected
    assert result.eligibility_notes


# --- § 2 BEEG replacement rate -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("net", "rate"),
    [
        (1100, 0.67),  # between €1,000 and €1,200: default
        (1000, 0.67),
        (1200, 0.67),
        (999, 0.67),  # €1 below: no FULL €2 step yet
        (998, 0.671),
        (800, 0.77),  # 100 steps of €2 -> +10 pp
        (340, 1.0),  # would be 1.00 exactly
        (100, 1.0),  # capped at 100 %
        (1220, 0.66),  # 10 steps above €1,200 -> -1 pp
        (1240, 0.65),
        (5000, 0.65),  # floor at 65 %
    ],
)
def test_replacement_rate_slide(net: float, rate: float) -> None:
    assert replacement_rate(net, load_rules().elterngeld) == pytest.approx(rate)


@pytest.mark.parametrize(
    ("net", "amount"),
    [
        (2000, 1300.0),  # 65 %
        (1100, 737.0),  # 67 %
        (800, 616.0),  # 77 %
        (0, 300.0),  # no income -> minimum
        (250, 300.0),  # 100 % of 250 is below the minimum
        (2770, 1800.0),  # 65 % of 2,770 = 1,800.50 -> maximum
        (6000, 1800.0),  # maximum
    ],
)
def test_basiselterngeld_amount_min_max(net: float, amount: float) -> None:
    result = _elterngeld(net, taxable_household_income_last_year=90_000)
    assert result.elterngeld_basis_monthly_estimate_eur == pytest.approx(amount)
    assert result.elterngeld_months_basis == 14


def test_income_cap_175k_means_no_elterngeld() -> None:
    result = _elterngeld(4000, taxable_household_income_last_year=175_001)
    assert result.elterngeld_basis_monthly_estimate_eur == 0
    assert result.elterngeld_months_basis == 0
    assert any("175,000" in n for n in result.eligibility_notes)


def test_income_exactly_at_cap_still_qualifies() -> None:
    result = _elterngeld(4000, taxable_household_income_last_year=175_000)
    assert result.elterngeld_basis_monthly_estimate_eur == 1800


def test_unknown_taxable_income_adds_cap_caveat() -> None:
    result = _elterngeld(2000)
    assert any("Income cap not checked" in c for c in result.caveats)


def test_births_before_cap_rule_are_refused() -> None:
    result = estimate_family_benefits(
        FamilyBenefitsInput(
            children_count=1,
            include_elterngeld=True,
            child_birth_date=date(2025, 3, 31),
            avg_monthly_net_income_before_birth=2000,
        ),
        today=TODAY,
    )
    assert isinstance(result, ToolError)
    assert "outside" in result.error


def test_pending_reform_caveat_only_for_births_from_2027_11_01() -> None:
    before = _ok(
        children_count=1,
        include_elterngeld=True,
        child_birth_date=date(2027, 10, 31),
        avg_monthly_net_income_before_birth=2000,
    )
    after = _ok(
        children_count=1,
        include_elterngeld=True,
        child_birth_date=date(2027, 11, 1),
        avg_monthly_net_income_before_birth=2000,
    )
    assert not any("Pending change" in c for c in before.caveats)
    assert any("Pending change" in c and "NOT law" in c for c in after.caveats)


def test_elterngeld_missing_inputs_return_needs() -> None:
    result = estimate_family_benefits(FamilyBenefitsInput(children_count=1, include_elterngeld=True), today=TODAY)
    assert isinstance(result, ToolError)
    assert result.needs == ["child_birth_date", "avg_monthly_net_income_before_birth"]


def test_tool_rejects_too_many_children_as_data() -> None:
    payload = json.loads(estimate_family_benefits_tool.invoke({"children_count": 20}))
    assert payload["needs"] == ["children_count"]

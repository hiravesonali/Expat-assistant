"""Statutory deadline calculator."""

import json
from datetime import date

import pytest

from expat.tools._common import ToolError
from expat.tools.deadlines import DeadlineInput, DeadlineResult, calculate_deadline, calculate_deadline_tool

TODAY = date(2026, 11, 17)


def _ok(procedure: str, event_date: date, as_of: date = TODAY) -> DeadlineResult:
    result = calculate_deadline(DeadlineInput(procedure=procedure, event_date=event_date, as_of=as_of))
    assert isinstance(result, DeadlineResult), result
    return result


def test_anmeldung_is_14_days_after_move_in() -> None:
    result = _ok("anmeldung", date(2026, 11, 10))
    assert result.due_date == date(2026, 11, 24)
    assert result.direction == "after"
    assert result.days_remaining == 7
    assert result.is_overdue is False
    assert result.legal_basis == ["§ 17 Abs. 1 BMG"]
    assert "1,000" in (result.consequences or "")
    assert any("appointment" in c for c in result.caveats)


def test_anmeldung_overdue() -> None:
    result = _ok("anmeldung", date(2026, 10, 1))
    assert result.due_date == date(2026, 10, 15)
    assert result.is_overdue is True
    assert result.days_remaining is not None and result.days_remaining < 0


def test_abmeldung() -> None:
    result = _ok("abmeldung", date(2026, 12, 20))
    assert result.due_date == date(2027, 1, 3)
    assert result.legal_basis == ["§ 17 Abs. 2 BMG"]


@pytest.mark.parametrize(
    ("birth", "due"),
    [
        (date(2026, 3, 10), date(2026, 9, 30)),  # apply by end of September -> March still paid
        (date(2026, 8, 31), date(2027, 2, 28)),  # crosses the year
    ],
)
def test_kindergeld_retroactive_six_months(birth: date, due: date) -> None:
    result = _ok("kindergeld_retroactive", birth)
    assert result.due_date == due
    assert result.legal_basis == ["§ 66 Abs. 3 EStG"]


def test_elterngeld_retroactive_three_life_months() -> None:
    # Life month 4 runs 2026-06-10..2026-07-09; an application in it still covers life months 1-3.
    result = _ok("elterngeld_retroactive", date(2026, 3, 10))
    assert result.due_date == date(2026, 7, 9)
    assert result.direction == "within"


def test_elterngeld_end_of_month_birth_gets_extra_caveat() -> None:
    result = _ok("elterngeld_retroactive", date(2026, 1, 31))
    assert result.due_date == date(2026, 5, 30)
    assert any("29th-31st" in c for c in result.caveats)


def test_residence_permit_extension_recommends_8_weeks_early() -> None:
    result = _ok("residence_permit_extension", date(2027, 6, 30))
    assert result.due_date == date(2027, 6, 30)
    assert result.recommended_by == date(2027, 5, 5)
    assert result.direction == "before"
    assert any("7 months" in c for c in result.caveats)


def test_rundfunkbeitrag_has_no_fixed_due_date() -> None:
    result = _ok("rundfunkbeitrag_registration", date(2026, 11, 12))
    assert result.due_date is None
    assert result.days_remaining is None
    assert result.is_overdue is False
    assert any("2026-11-01" in c for c in result.caveats)
    assert any("Pending change" in c for c in result.caveats)


def test_event_before_rule_validity_is_refused() -> None:
    result = calculate_deadline(DeadlineInput(procedure="anmeldung", event_date=date(2010, 1, 1)))
    assert isinstance(result, ToolError)


def test_as_of_defaults_to_today() -> None:
    result = calculate_deadline(DeadlineInput(procedure="anmeldung", event_date=date(2026, 11, 10)), today=TODAY)
    assert isinstance(result, DeadlineResult)
    assert result.days_remaining == 7


def test_tool_unknown_procedure_returns_needs() -> None:
    payload = json.loads(calculate_deadline_tool.invoke({"procedure": "visa_on_arrival", "event_date": "2026-11-01"}))
    assert payload["needs"] == ["procedure"]


def test_tool_missing_event_date_returns_needs() -> None:
    payload = json.loads(calculate_deadline_tool.invoke({"procedure": "anmeldung"}))
    assert payload["needs"] == ["event_date"]

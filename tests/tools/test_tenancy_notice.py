"""§ 573c BGB notice calculator. Dates are real 2026/2027 calendar dates in Bavaria (BY)."""

import json
from datetime import date

import pytest
from langchain_core.messages import ToolMessage
from pydantic import ValidationError

from expat.tools._common import ToolError
from expat.tools.tenancy_notice import (
    NoticeInput,
    NoticeResult,
    calculate_tenancy_notice,
    calculate_tenancy_notice_tool,
    nth_working_day,
)


def _ok(**kwargs: object) -> NoticeResult:
    result = calculate_tenancy_notice(NoticeInput.model_validate(kwargs))
    assert isinstance(result, NoticeResult), result
    return result


# --- 3rd working day -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("year", "month", "expected", "why"),
    [
        # Jan 1 (Thu) holiday, Jan 2 Fri = 1, Sat/Sun skipped, Jan 5 Mon = 2, Jan 6 Epiphany (BY), Jan 7 = 3.
        (2026, 1, date(2026, 1, 7), "New Year + Saturday + Epiphany in BY"),
        # Jan 1 (Fri) holiday, weekend, Jan 4 Mon = 1, Jan 5 = 2, Jan 6 Epiphany, Jan 7 = 3.
        (2027, 1, date(2027, 1, 7), "New Year + weekend + Epiphany in BY"),
        # Apr 1 Thu = 1, Apr 2 Fri = 2, Apr 3 is a SATURDAY (doesn't count), Apr 5 Mon = 3.
        (2027, 4, date(2027, 4, 5), "Saturday does not count (BGH VIII ZR 291/09)"),
        # Oct 1 Thu = 1, Oct 2 Fri = 2, Oct 3 Sat (and German Unity Day), Oct 5 Mon = 3.
        (2026, 10, date(2026, 10, 5), "Saturday holiday"),
        # Nov 1 Sun (All Saints), Nov 2 Mon = 1 ... Nov 4 = 3.
        (2026, 11, date(2026, 11, 4), "All Saints on a Sunday"),
        # May 1 2026 Fri holiday, weekend, May 4 = 1, May 5 = 2, May 6 = 3.
        (2026, 5, date(2026, 5, 6), "Labour Day"),
    ],
)
def test_third_working_day_in_bavaria(year: int, month: int, expected: date, why: str) -> None:
    assert nth_working_day(year, month, 3, "BY") == expected, why


def test_saturday_would_shift_deadline_if_it_counted() -> None:
    """Documents why the BGH ruling matters: counting Saturday would make the deadline 2 days earlier."""
    assert nth_working_day(2027, 4, 3, "BY", saturday_counts=True) == date(2027, 4, 3)
    assert nth_working_day(2027, 4, 3, "BY") == date(2027, 4, 5)


def test_epiphany_is_only_a_holiday_in_some_states() -> None:
    assert nth_working_day(2026, 1, 3, "BY") == date(2026, 1, 7)
    assert nth_working_day(2026, 1, 3, "BE") == date(2026, 1, 6)


# --- tenant ------------------------------------------------------------------------------------------


def test_tenant_notice_received_on_saturday_shifted_deadline_is_in_time() -> None:
    result = _ok(party="tenant", tenancy_start=date(2020, 1, 1), notice_date=date(2027, 4, 5))
    assert result.notice_period_months == 3
    assert result.receipt_deadline_this_month == date(2027, 4, 5)
    assert result.received_in_time_for_this_month is True
    assert result.tenancy_end_date == date(2027, 6, 30)


def test_tenant_notice_one_day_late_shifts_end_by_a_month() -> None:
    result = _ok(party="tenant", tenancy_start=date(2020, 1, 1), notice_date=date(2027, 4, 6))
    assert result.received_in_time_for_this_month is False
    assert result.tenancy_end_date == date(2027, 7, 31)


def test_tenant_period_is_always_three_months_even_after_long_tenancy() -> None:
    result = _ok(party="tenant", tenancy_start=date(2010, 1, 1), notice_date=date(2026, 1, 7))
    assert result.notice_period_months == 3
    assert result.tenancy_end_date == date(2026, 3, 31)


def test_notice_date_defaults_to_today() -> None:
    inp = NoticeInput(party="tenant", tenancy_start=date(2020, 1, 1))
    result = calculate_tenancy_notice(inp, today=date(2026, 11, 17))
    assert isinstance(result, NoticeResult)
    assert result.notice_date == date(2026, 11, 17)
    assert result.tenancy_end_date == date(2027, 2, 28)


# --- landlord ----------------------------------------------------------------------------------------


def test_landlord_six_year_tenancy_late_in_month() -> None:
    """The docs/tools.md example: 6 years, notice received 2026-11-17 -> 6 months, ends 2027-05-31."""
    result = _ok(party="landlord", tenancy_start=date(2020, 11, 1), notice_date=date(2026, 11, 17))
    assert result.tenancy_duration_years == 6
    assert result.notice_period_months == 6
    assert result.receipt_deadline_this_month == date(2026, 11, 4)
    assert result.received_in_time_for_this_month is False
    assert result.tenancy_end_date == date(2027, 5, 31)
    assert any("§ 573 BGB" in c for c in result.caveats)


def test_landlord_six_year_tenancy_in_time() -> None:
    result = _ok(party="landlord", tenancy_start=date(2020, 11, 1), notice_date=date(2026, 11, 4))
    assert result.tenancy_end_date == date(2027, 4, 30)


@pytest.mark.parametrize(
    ("tenancy_start", "months"),
    [
        (date(2021, 11, 18), 3),  # 4 years and 364 days
        (date(2021, 11, 17), 6),  # exactly 5 years at receipt
        (date(2018, 11, 18), 6),  # 7 years
        (date(2018, 11, 17), 9),  # exactly 8 years
        (date(2006, 1, 1), 9),  # 20 years: no further tier
    ],
)
def test_landlord_tiers(tenancy_start: date, months: int) -> None:
    result = _ok(party="landlord", tenancy_start=tenancy_start, notice_date=date(2026, 11, 17))
    assert result.notice_period_months == months


# --- caveats and non-calculated cases ----------------------------------------------------------------


def test_written_form_caveat_is_always_present() -> None:
    result = _ok(party="tenant", tenancy_start=date(2020, 1, 1), notice_date=date(2026, 3, 2))
    assert any("§ 568" in c for c in result.caveats)
    assert result.legal_basis[0] == "§ 573c Abs. 1 BGB"
    assert result.source_urls == ["https://www.gesetze-im-internet.de/bgb/__573c.html"]
    assert result.rules_version


@pytest.mark.parametrize("contract_type", ["fixed_term", "furnished_room_in_landlord_flat"])
def test_special_contracts_return_caveat_without_calculation(contract_type: str) -> None:
    result = _ok(
        party="tenant", tenancy_start=date(2024, 1, 1), notice_date=date(2026, 3, 2), contract_type=contract_type
    )
    assert result.tenancy_end_date is None
    assert result.notice_period_months is None
    assert result.explanation in result.caveats


def test_furnished_room_cites_573c_paragraph_3() -> None:
    result = _ok(
        party="tenant",
        tenancy_start=date(2024, 1, 1),
        notice_date=date(2026, 3, 2),
        contract_type="furnished_room_in_landlord_flat",
    )
    assert "§ 573c Abs. 3 BGB" in result.legal_basis


# --- errors as data ----------------------------------------------------------------------------------


def test_start_after_notice_returns_error_not_exception() -> None:
    result = calculate_tenancy_notice(
        NoticeInput(party="tenant", tenancy_start=date(2027, 1, 1), notice_date=date(2026, 1, 1))
    )
    assert isinstance(result, ToolError)
    assert "tenancy_start" in result.needs


def test_date_before_rule_validity_is_refused() -> None:
    result = calculate_tenancy_notice(
        NoticeInput(party="tenant", tenancy_start=date(1995, 1, 1), notice_date=date(2000, 1, 3))
    )
    assert isinstance(result, ToolError)
    assert "outside" in result.error


def test_unknown_state_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NoticeInput(party="tenant", tenancy_start=date(2020, 1, 1), state="XX")


# --- LangChain wrapper -------------------------------------------------------------------------------


def test_tool_missing_input_returns_needs() -> None:
    content = calculate_tenancy_notice_tool.invoke({"party": "landlord"})
    payload = json.loads(content)
    assert payload["needs"] == ["tenancy_start"]
    assert "error" in payload


def test_tool_call_returns_json_content_and_typed_artifact() -> None:
    message = calculate_tenancy_notice_tool.invoke(
        {
            "type": "tool_call",
            "id": "call_1",
            "name": "calculate_tenancy_notice",
            "args": {"party": "landlord", "tenancy_start": "2020-11-01", "notice_date": "2026-11-17"},
        }
    )
    assert isinstance(message, ToolMessage)
    assert json.loads(message.content)["tenancy_end_date"] == "2027-05-31"
    assert isinstance(message.artifact, NoticeResult)

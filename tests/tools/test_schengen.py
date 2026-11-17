"""Schengen rolling 90/180-day calculator."""

import json
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from expat.tools.schengen import (
    SchengenInput,
    SchengenResult,
    Stay,
    schengen_days_calculator,
    schengen_days_calculator_tool,
)

CHECK = date(2026, 11, 17)  # window: 2026-05-22 .. 2026-11-17 (180 days inclusive)


def _ok(stays: list[tuple[date, date]], check_date: date = CHECK) -> SchengenResult:
    inp = SchengenInput(stays=[Stay(entry=a, exit=b) for a, b in stays], check_date=check_date)
    result = schengen_days_calculator(inp)
    assert isinstance(result, SchengenResult), result
    return result


def test_window_is_180_days_inclusive() -> None:
    result = _ok([])
    assert result.window_start == date(2026, 5, 22)
    assert result.window_end == CHECK
    assert (result.window_end - result.window_start).days + 1 == 180
    assert result.days_used_in_window == 0
    assert result.days_remaining == 90


def test_entry_and_exit_day_both_count() -> None:
    assert _ok([(date(2026, 10, 1), date(2026, 10, 1))]).days_used_in_window == 1
    assert _ok([(date(2026, 10, 1), date(2026, 10, 10))]).days_used_in_window == 10


def test_stay_partly_before_window_counts_only_days_inside() -> None:
    # May 20..25: only May 22, 23, 24, 25 are inside the window.
    assert _ok([(date(2026, 5, 20), date(2026, 5, 25))]).days_used_in_window == 4


def test_stay_ending_the_day_before_window_start_counts_zero() -> None:
    assert _ok([(date(2026, 5, 1), date(2026, 5, 21))]).days_used_in_window == 0


def test_exactly_90_days_is_allowed() -> None:
    entry = date(2026, 8, 1)
    result = _ok([(entry, entry + timedelta(days=89))])
    assert result.days_used_in_window == 90
    assert result.days_remaining == 0
    assert result.overstay is False


def test_91_days_is_an_overstay_on_day_91() -> None:
    entry = date(2026, 8, 1)
    result = _ok([(entry, entry + timedelta(days=90))])
    assert result.overstay is True
    assert result.first_overstay_day == entry + timedelta(days=90)
    assert result.days_remaining == 0


def test_overstay_detected_even_if_check_date_window_looks_fine() -> None:
    """The rule applies on every day of a stay, not only on the check date."""
    result = _ok([(date(2026, 1, 1), date(2026, 4, 30))], check_date=date(2026, 11, 17))
    assert result.days_used_in_window == 0
    assert result.overstay is True
    assert result.first_overstay_day == date(2026, 4, 1)


def test_planned_stay_without_history_can_last_90_days() -> None:
    entry = date(2026, 12, 1)
    result = _ok([(entry, date(2027, 1, 15))])
    assert result.latest_allowed_exit_for_planned_stay == date(2027, 2, 28)
    assert result.overstay is False


def test_planned_stay_after_previous_visit_uses_rolling_window() -> None:
    """60 days in June/July: the planned stay from Nov 1 can last until Jan 29 2027.

    Up to Nov 27 the count grows to 87; then each new day replaces a June/July day leaving the window,
    so the count stays at 87 until July 30 leaves the window (Jan 26), and the limit is hit after 3 more days.
    """
    result = _ok(
        [(date(2026, 6, 1), date(2026, 7, 30)), (date(2026, 11, 1), date(2026, 12, 15))],
        check_date=date(2026, 10, 15),
    )
    assert result.days_used_in_window == 60
    assert result.latest_allowed_exit_for_planned_stay == date(2027, 1, 29)


def test_entry_impossible_when_limit_already_reached() -> None:
    result = _ok(
        [(date(2026, 8, 1), date(2026, 10, 29)), (date(2026, 10, 31), date(2026, 11, 5))],
        check_date=date(2026, 10, 30),
    )
    assert result.latest_allowed_exit_for_planned_stay is None
    assert result.overstay is True


def test_past_stays_only_have_no_planned_exit() -> None:
    assert _ok([(date(2026, 9, 1), date(2026, 9, 10))]).latest_allowed_exit_for_planned_stay is None


def test_stays_are_sorted() -> None:
    inp = SchengenInput(
        stays=[
            Stay(entry=date(2026, 10, 1), exit=date(2026, 10, 2)),
            Stay(entry=date(2026, 6, 1), exit=date(2026, 6, 2)),
        ]
    )
    assert inp.stays[0].entry == date(2026, 6, 1)


@pytest.mark.parametrize(
    "stays",
    [
        [{"entry": "2026-06-10", "exit": "2026-06-01"}],  # exit before entry
        [{"entry": "2026-06-01", "exit": "2026-06-10"}, {"entry": "2026-06-05", "exit": "2026-06-20"}],  # overlap
        [{"entry": "2026-06-01", "exit": "2026-06-10"}, {"entry": "2026-06-10", "exit": "2026-06-20"}],  # shared day
    ],
)
def test_invalid_stays_are_rejected(stays: list[dict[str, str]]) -> None:
    with pytest.raises(ValidationError):
        SchengenInput.model_validate({"stays": stays})
    payload = json.loads(schengen_days_calculator_tool.invoke({"stays": stays, "check_date": "2026-11-17"}))
    assert payload["needs"] == ["stays"]


def test_resident_permit_holder_gets_explanation_not_count() -> None:
    result = schengen_days_calculator(SchengenInput(stays=[], traveller="resident_permit_holder", check_date=CHECK))
    assert isinstance(result, SchengenResult)
    assert result.days_used_in_window is None
    assert "Art. 21" in result.legal_basis[0]
    assert "OTHER Schengen states" in result.explanation
    assert any("Medium confidence" in c for c in result.caveats)


def test_tool_returns_citable_json() -> None:
    payload = json.loads(
        schengen_days_calculator_tool.invoke(
            {"stays": [{"entry": "2026-10-01", "exit": "2026-10-10"}], "check_date": "2026-11-17"}
        )
    )
    assert payload["days_used_in_window"] == 10
    assert payload["source_urls"] and payload["rules_version"] and payload["legal_basis"]

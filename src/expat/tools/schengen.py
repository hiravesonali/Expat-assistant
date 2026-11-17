"""`schengen_days_calculator`: the rolling 90/180-day rule for short stays (e.g. visiting parents).

The rule (Art. 6 Abs. 1 Schengen Borders Code): on ANY day of a stay, the days spent in the Schengen area
during the 180-day window ending that day (inclusive) must not exceed 90. Entry and exit days both count.
Because the window rolls, "days remaining" is not simply 90 minus days used; this module checks every day.
"""

from datetime import date, timedelta
from itertools import pairwise
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from expat.tools._common import ToolError, ToolOutput, make_tool, outside_window
from expat.tools.rules import Rules, load_rules

MAX_STAY_DAYS = 3 * 366  # sanity bound: a longer "short stay" is surely a typo


class Stay(BaseModel):
    entry: date = Field(description="Entry date into the Schengen area (counts as a day of stay).")
    exit: date = Field(description="Exit date from the Schengen area (counts as a day of stay).")

    @model_validator(mode="after")
    def _exit_not_before_entry(self) -> "Stay":
        if self.exit < self.entry:
            raise ValueError(f"exit {self.exit} is before entry {self.entry}")
        if (self.exit - self.entry).days > MAX_STAY_DAYS:
            raise ValueError(f"stay {self.entry}..{self.exit} is implausibly long")
        return self

    @property
    def days(self) -> int:
        return (self.exit - self.entry).days + 1


class SchengenInput(BaseModel):
    stays: list[Stay] = Field(max_length=100, description="All past and planned stays in the Schengen area.")
    check_date: date | None = Field(default=None, description="Day to evaluate the window for. Defaults to today.")
    traveller: Literal["visitor_short_stay", "resident_permit_holder"] = Field(
        default="visitor_short_stay",
        description="'visitor_short_stay' for visa-free or Schengen-visa visitors; "
        "'resident_permit_holder' for holders of a German residence permit.",
    )

    @field_validator("stays")
    @classmethod
    def _no_overlaps(cls, stays: list[Stay]) -> list[Stay]:
        """Overlapping stays would double-count days; sort them so later code can rely on the order."""
        ordered = sorted(stays, key=lambda s: s.entry)
        for previous, current in pairwise(ordered):
            if current.entry <= previous.exit:
                raise ValueError(
                    f"stays overlap or share a day ({previous.entry}..{previous.exit} and "
                    f"{current.entry}..{current.exit}); merge them into one stay"
                )
        return ordered


class SchengenResult(ToolOutput):
    traveller: Literal["visitor_short_stay", "resident_permit_holder"]
    check_date: date
    window_start: date | None
    window_end: date | None
    days_used_in_window: int | None
    days_remaining: int | None
    latest_allowed_exit_for_planned_stay: date | None
    overstay: bool | None
    first_overstay_day: date | None
    explanation: str


def days_in_window(stays: list[Stay], window_end: date, window_days: int) -> int:
    """Stay days inside [window_end - (window_days - 1), window_end], both ends inclusive."""
    window_start = window_end - timedelta(days=window_days - 1)
    total = 0
    for stay in stays:
        overlap = (min(stay.exit, window_end) - max(stay.entry, window_start)).days + 1
        total += max(0, overlap)
    return total


def _first_overstay_day(stays: list[Stay], max_days: int, window_days: int) -> date | None:
    """Check the rule on every day of every stay (the rule applies to each day, not just today)."""
    for stay in stays:
        day = stay.entry
        while day <= stay.exit:
            if days_in_window(stays, day, window_days) > max_days:
                return day
            day += timedelta(days=1)
    return None


def _latest_exit(previous: list[Stay], entry: date, max_days: int, window_days: int) -> date | None:
    """Last exit day such that every day from `entry` to it respects the rule; None if entry is already too much.

    Grow the planned stay one day at a time; the first day that breaks the limit ends the search. Bounded,
    because staying continuously breaks the limit after at most `max_days + 1` days.
    """
    day = entry
    for _ in range(max_days + 1):
        if days_in_window([*previous, Stay(entry=entry, exit=day)], day, window_days) > max_days:
            return day - timedelta(days=1) if day > entry else None
        day += timedelta(days=1)
    return day - timedelta(days=1)  # pragma: no cover - unreachable, kept as a safe fallback


def schengen_days_calculator(
    inp: SchengenInput, *, today: date | None = None, rules: Rules | None = None
) -> SchengenResult | ToolError:
    """Pure function: days used, days remaining, overstay check and the latest exit for a planned stay."""
    rules = rules or load_rules()
    rule = rules.schengen
    check_date = inp.check_date or today or date.today()
    if not rule.covers(check_date):
        return outside_window(rule, check_date, "the Schengen 90/180-day rule")

    if inp.traveller == "resident_permit_holder":
        explanation = (
            "A valid German residence permit allows you to stay in Germany without the 90/180-day limit. "
            "For trips to OTHER Schengen states, a residence permit plus passport allows stays of up to 90 days "
            "in any 180-day period (Art. 21 CISA). To check such trips, list only the days spent in other "
            "Schengen states and use traveller='visitor_short_stay'."
        )
        return SchengenResult(
            traveller=inp.traveller,
            check_date=check_date,
            window_start=None,
            window_end=None,
            days_used_in_window=None,
            days_remaining=None,
            latest_allowed_exit_for_planned_stay=None,
            overstay=None,
            first_overstay_day=None,
            explanation=explanation,
            legal_basis=[rule.resident_legal_basis],
            source_urls=[rule.source_url],
            rules_version=rules.version,
            caveats=[
                "Medium confidence: Art. 21 CISA applies to trips to other Schengen states; carry your passport "
                "and residence permit. Long absences from Germany (over 6 months) can end a permit "
                "(§ 51 Abs. 1 Nr. 7 AufenthG).",
            ],
        )

    window_start = check_date - timedelta(days=rule.window_days - 1)
    used = days_in_window(inp.stays, check_date, rule.window_days)
    first_overstay = _first_overstay_day(inp.stays, rule.max_days, rule.window_days)

    # The "planned" stay is the last stay if it is ongoing or in the future relative to check_date.
    latest_exit: date | None = None
    planned = inp.stays[-1] if inp.stays and inp.stays[-1].exit >= check_date else None
    if planned is not None:
        latest_exit = _latest_exit(inp.stays[:-1], planned.entry, rule.max_days, rule.window_days)

    explanation = (
        f"In the 180-day window {window_start.isoformat()} to {check_date.isoformat()} you spent {used} days in "
        f"the Schengen area ({max(0, rule.max_days - used)} of {rule.max_days} left on that day)."
    )
    if planned is not None:
        explanation += (
            f" For the stay starting {planned.entry.isoformat()}, the latest allowed exit is "
            f"{latest_exit.isoformat() if latest_exit else 'none (entry would already exceed the limit)'}."
        )
    if first_overstay:
        explanation += f" The 90-day limit is exceeded on {first_overstay.isoformat()}."

    return SchengenResult(
        traveller=inp.traveller,
        check_date=check_date,
        window_start=window_start,
        window_end=check_date,
        days_used_in_window=used,
        days_remaining=max(0, rule.max_days - used),
        latest_allowed_exit_for_planned_stay=latest_exit,
        overstay=first_overstay is not None,
        first_overstay_day=first_overstay,
        explanation=explanation,
        legal_basis=[rule.legal_basis],
        source_urls=[rule.source_url],
        rules_version=rules.version,
        caveats=[
            "Entry and exit days both count as days of stay.",
            "days_remaining is for the check date only; older days leave the rolling window over time, so use "
            "latest_allowed_exit_for_planned_stay for a planned trip.",
            "Assumes visa-free travel or a Schengen visa with enough validity; a visa may allow fewer days. "
            "Cross-check with the EU Commission's short-stay calculator.",
        ],
    )


schengen_days_calculator_tool = make_tool(
    name="schengen_days_calculator",
    description=(
        "Apply the Schengen 90/180-day rule to a list of stays: days used in the rolling window, days left, "
        "overstay detection and the latest allowed exit date for a planned stay. Use for visitors (e.g. "
        "non-EU parents visiting) or when a German residence permit holder asks about travel limits. "
        "Never count these days yourself."
    ),
    args_schema=SchengenInput,
    fn=schengen_days_calculator,
)

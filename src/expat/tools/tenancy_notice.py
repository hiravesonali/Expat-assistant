"""`calculate_tenancy_notice`: notice periods for residential leases (§ 573c BGB).

The law in one sentence: notice received by the 3rd working day of a month ends the tenancy at the end of
the month after next (tenant: always 3 months; landlord: 3 / 6 / 9 months after 0 / 5 / 8 years).

Why this is code and not LLM reasoning: "3rd working day" depends on weekends, Bavarian public holidays and
a BGH ruling that Saturdays do NOT count (BGH VIII ZR 291/09). LLMs get exactly this kind of calendar
arithmetic wrong.
"""

from datetime import date, timedelta
from functools import lru_cache
from typing import Literal

import holidays
from pydantic import BaseModel, Field, field_validator

from expat.tools._common import ToolError, ToolOutput, make_tool, outside_window
from expat.tools._dates import full_years_between, last_day_of_month, shift_month
from expat.tools.rules import Rules, load_rules

ContractType = Literal["unlimited", "fixed_term", "furnished_room_in_landlord_flat"]


class NoticeInput(BaseModel):
    """Arguments the answer model fills in. Descriptions are shown to the model in the tool schema."""

    party: Literal["tenant", "landlord"] = Field(
        description=(
            "Who GIVES (sends) the notice, not who the user is. 'landlord' if the landlord terminates the lease "
            "(e.g. 'my landlord gave me notice', Eigenbedarf), even though the user is the tenant. 'tenant' if the "
            "user wants to move out. The two notice periods differ (landlord: 3/6/9 months by tenancy length)."
        )
    )
    tenancy_start: date | None = Field(
        default=None,
        description="Date the tenant got the flat. Needed ONLY when the landlord gives notice (3/6/9 months by "
        "tenancy length). A tenant's notice period is always 3 months: leave it empty, don't ask the user for it.",
    )
    notice_date: date | None = Field(
        default=None, description="Date the notice letter is RECEIVED by the other party. Defaults to today."
    )
    contract_type: ContractType = Field(default="unlimited", description="Type of lease contract.")
    state: str = Field(default="BY", description="German state code for public holidays, e.g. 'BY' for Bavaria.")

    @field_validator("state")
    @classmethod
    def _known_state(cls, value: str) -> str:
        """Reject unknown states early, so the holiday lookup can't silently use the wrong calendar."""
        value = value.upper()
        if value not in holidays.Germany.subdivisions:
            raise ValueError(f"unknown German state code {value!r}")
        return value


class NoticeResult(ToolOutput):
    """Date fields are None when the tool deliberately does not calculate (fixed term, furnished room)."""

    party: Literal["tenant", "landlord"]
    contract_type: ContractType
    tenancy_duration_years: int | None  # None when a tenant gives notice without a start date (not needed)
    notice_date: date
    notice_period_months: int | None
    receipt_deadline_this_month: date | None
    received_in_time_for_this_month: bool | None
    tenancy_end_date: date | None
    explanation: str


@lru_cache(maxsize=64)
def _holidays_for(state: str, year: int) -> holidays.HolidayBase:
    """Public holidays of one state and year (cached; the holidays package builds them on demand).

    Note: for 'BY' the package includes Epiphany (Jan 6) and All Saints (Nov 1). Assumption Day (Aug 15) is
    regional in Bavaria, but it can never be one of the first three working days, so it doesn't matter here.
    """
    return holidays.country_holidays("DE", subdiv=state, years=year)


def is_working_day(day: date, state: str, *, saturday_counts: bool = False) -> bool:
    """Mon-Fri (plus Saturday only if `saturday_counts`) and not a public holiday in `state`."""
    last_workday = 5 if saturday_counts else 4  # date.weekday(): Monday=0 ... Sunday=6
    return day.weekday() <= last_workday and day not in _holidays_for(state, day.year)


def nth_working_day(year: int, month: int, n: int, state: str, *, saturday_counts: bool = False) -> date:
    """The n-th working day of a month, e.g. n=3 is the § 573c receipt deadline."""
    day = date(year, month, 1)
    found = 0
    while True:
        if is_working_day(day, state, saturday_counts=saturday_counts):
            found += 1
            if found == n:
                return day
        day += timedelta(days=1)


def _landlord_months(rules: Rules, years: int) -> int:
    """Last tier whose `min_years` is reached (tiers are validated as sorted by the rules loader)."""
    months = rules.tenancy_notice.landlord_months[0].months
    for tier in rules.tenancy_notice.landlord_months:
        if years >= tier.min_years:
            months = tier.months
    return months


def calculate_tenancy_notice(
    inp: NoticeInput, *, today: date | None = None, rules: Rules | None = None
) -> NoticeResult | ToolError:
    """Pure function: compute the receipt deadline and tenancy end date (or explain why it can't).

    `today` and `rules` are injectable so tests are deterministic and need no file system tricks.
    """
    rules = rules or load_rules()
    rule = rules.tenancy_notice
    notice_date = inp.notice_date or today or date.today()

    if inp.party == "landlord" and inp.tenancy_start is None:
        return ToolError(
            error="The landlord's notice period depends on how long the tenancy has lasted; tenancy_start is needed.",
            needs=["tenancy_start"],
        )
    if inp.tenancy_start is not None and inp.tenancy_start > notice_date:
        return ToolError(
            error="tenancy_start is after the notice date; please check both dates.",
            needs=["tenancy_start", "notice_date"],
        )
    if not rule.covers(notice_date):
        return outside_window(rule, notice_date, "tenancy notice periods (§ 573c BGB)")

    years = full_years_between(inp.tenancy_start, notice_date) if inp.tenancy_start else None
    caveats = [
        "Notice must be in written form with a handwritten signature (§ 568 Abs. 1 BGB); email, fax or "
        "messenger messages are not valid.",
        "What counts is the date the letter is RECEIVED, not sent. Use hand delivery with a witness or "
        "registered mail (Einwurf-Einschreiben) and keep proof.",
        "A contractual waiver of notice (Kündigungsverzicht, usually at most 4 years) can block ordinary "
        "notice until it expires.",
    ]
    if inp.party == "landlord":
        caveats.append(
            "A landlord also needs a legitimate interest, e.g. personal need (Eigenbedarf) (§ 573 BGB), and "
            "the tenant may object on grounds of hardship (§ 574 BGB)."
        )
    caveats += [f"Pending change: {p.summary}" for p in rules.pending("tenancy")]
    base = {
        "party": inp.party,
        "contract_type": inp.contract_type,
        "tenancy_duration_years": years,
        "notice_date": notice_date,
        "legal_basis": [rule.legal_basis, "§ 568 Abs. 1 BGB"],
        "source_urls": [rule.source_url],
        "rules_version": rules.version,
    }

    if inp.contract_type != "unlimited":
        if inp.contract_type == "fixed_term":
            explanation = (
                "Fixed-term leases (Zeitmietvertrag, § 575 BGB) cannot normally be ended by ordinary notice "
                "before the agreed end date, so no notice period was calculated."
            )
            legal = ["§ 575 BGB"]
        else:
            explanation = (
                "For a furnished room inside the landlord's own flat, § 573c Abs. 3 BGB allows shorter notice "
                "(by the 15th of a month to the end of that month). This tool does not calculate that case."
            )
            legal = ["§ 573c Abs. 3 BGB", "§ 549 Abs. 2 Nr. 2 BGB"]
        base["legal_basis"] = [*legal, "§ 568 Abs. 1 BGB"]
        return NoticeResult(
            **base,
            notice_period_months=None,
            receipt_deadline_this_month=None,
            received_in_time_for_this_month=None,
            tenancy_end_date=None,
            explanation=explanation,
            caveats=[explanation, *caveats],
        )

    # years is set for the landlord (checked above); a tenant always has the flat rate
    months = rule.tenant_months if inp.party == "tenant" else _landlord_months(rules, years or 0)
    deadline = nth_working_day(
        notice_date.year,
        notice_date.month,
        rule.grace_working_days,
        inp.state,
        saturday_counts=rule.saturday_is_working_day,
    )
    in_time = notice_date <= deadline
    # The notice month itself counts as month 1 if received in time; otherwise counting starts next month.
    start_offset = 0 if in_time else 1
    end_year, end_month = shift_month(notice_date.year, notice_date.month, start_offset + months - 1)
    end = last_day_of_month(end_year, end_month)

    explanation = (
        f"{inp.party.capitalize()} notice period: {months} months. Notice must be received by "
        f"{deadline.isoformat()} (3rd working day; Saturdays, Sundays and public holidays in {inp.state} "
        f"don't count). Received on {notice_date.isoformat()}: "
        f"{'in time' if in_time else 'too late for this month, so it counts from next month'}; "
        f"the tenancy ends on {end.isoformat()}."
    )
    if inp.party == "landlord":
        caveats.append(
            f"Landlord period based on {years} full years of tenancy at the date of receipt "
            "(+3 months after 5 and after 8 years)."
        )
    return NoticeResult(
        **base,
        notice_period_months=months,
        receipt_deadline_this_month=deadline,
        received_in_time_for_this_month=in_time,
        tenancy_end_date=end,
        explanation=explanation,
        caveats=caveats,
    )


calculate_tenancy_notice_tool = make_tool(
    name="calculate_tenancy_notice",
    description=(
        "Compute German residential tenancy notice dates (§ 573c BGB): the notice period in months, the "
        "3rd-working-day receipt deadline and the tenancy end date, for a tenant or a landlord. Use whenever "
        "the user asks when a tenancy ends, how long the notice period is, or by when a notice must arrive. "
        "Never compute these dates yourself. If the tenancy start date is unknown, ask the user. "
        "Set party to whoever SENDS the notice: a question like 'my landlord gave me notice' means "
        "party='landlord', even though the user is the tenant."
    ),
    args_schema=NoticeInput,
    fn=calculate_tenancy_notice,
)

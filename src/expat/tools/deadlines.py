"""`calculate_deadline`: statutory deadlines for the procedures in the corpus.

Each procedure maps to a `DeadlineRule` in `rules/2026.yaml`; the rule's `kind` selects the arithmetic.
Keeping the legal numbers in YAML and only the *kind of counting* in code means a law change is a YAML edit.
"""

from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from expat.tools._common import ToolError, ToolOutput, make_tool, outside_window
from expat.tools._dates import add_months, last_day_of_month, shift_month
from expat.tools.rules import DeadlineRule, Rules, load_rules

Procedure = Literal[
    "anmeldung",
    "abmeldung",
    "kindergeld_retroactive",
    "elterngeld_retroactive",
    "residence_permit_extension",
    "rundfunkbeitrag_registration",
]

EVENT_MEANING: dict[str, str] = {
    "anmeldung": "move-in date",
    "abmeldung": "move-out date",
    "kindergeld_retroactive": "child's birth date (or the first month of entitlement)",
    "elterngeld_retroactive": "child's birth date",
    "residence_permit_extension": "expiry date of the current residence permit",
    "rundfunkbeitrag_registration": "move-in date",
}


class DeadlineInput(BaseModel):
    procedure: Procedure = Field(description="Which deadline to compute.")
    event_date: date = Field(
        description=(
            "The triggering date: move-in date (anmeldung, rundfunkbeitrag_registration), move-out date "
            "(abmeldung), child's birth date (kindergeld_retroactive, elterngeld_retroactive) or permit expiry "
            "date (residence_permit_extension)."
        )
    )
    as_of: date | None = Field(default=None, description="Reference date for days remaining. Defaults to today.")


class DeadlineResult(ToolOutput):
    procedure: Procedure
    event_date: date
    due_date: date | None  # None for "without undue delay" (no fixed number of days)
    recommended_by: date | None = None  # earlier, practical target date (residence permit)
    direction: Literal["before", "after", "within"]
    days_remaining: int | None
    is_overdue: bool
    rule_text: str
    consequences: str | None
    # Retroactive benefits only: what an application arriving on `as_of` still gets (late is not "nothing").
    paid_from_if_applied_now: date | None = None
    months_lost_if_applied_now: int | None = None


WEEKEND_CAVEAT = (
    "If the last day falls on a weekend or public holiday, the deadline usually moves to the next working day "
    "(§ 31 Abs. 3 VwVfG, § 193 BGB); the date shown is not shifted, to be on the safe side."
)


def _due_date(rule: DeadlineRule, event: date) -> tuple[date | None, date | None, Literal["before", "after", "within"]]:
    """(due_date, recommended_by, direction) for one rule kind. All arithmetic lives here."""
    match rule.kind:
        case "days_after":
            # § 187 Abs. 1 BGB: the event day is not counted, so "14 days after 1 March" ends on 15 March.
            return event + timedelta(days=rule.amount), None, "after"
        case "calendar_months_retroactive":
            # Paid for the N months BEFORE the application month, so the event month is still covered if the
            # application arrives in month (event month + N). Due = the last day of that month.
            year, month = shift_month(event.year, event.month, rule.amount)
            return last_day_of_month(year, month), None, "within"
        case "life_months_retroactive":
            # Life month k runs from (birth + k-1 months) to (birth + k months - 1 day). Paying back N life
            # months means the application must arrive within life month N+1 to keep life month 1.
            return add_months(event, rule.amount + 1) - timedelta(days=1), None, "within"
        case "before_expiry":
            # The permit is valid through its expiry date, so that is the last possible day; `amount` is the
            # recommended lead time in days.
            return event, event - timedelta(days=rule.amount), "before"
        case "without_undue_delay":
            return None, None, "within"


def _paid_if_applied_on(rule: DeadlineRule, event: date, applied: date) -> tuple[date, int] | None:
    """(first day still paid, months lost) for an application arriving on `applied`; None for other kinds.

    Kindergeld: paid for the N calendar months before the application month (§ 70 Abs. 1 Satz 2 EStG), never
    before the month of the event. Elterngeld: paid for the N life months before the life month of the
    application (§ 7 Abs. 1 Satz 2 BEEG).
    """
    match rule.kind:
        case "calendar_months_retroactive":
            event_index = event.year * 12 + event.month - 1
            first_index = max(event_index, applied.year * 12 + applied.month - 1 - rule.amount)
            return date(first_index // 12, first_index % 12 + 1, 1), first_index - event_index
        case "life_months_retroactive":
            life_month = 1  # the life month the application arrives in
            while add_months(event, life_month) <= applied:
                life_month += 1
            first_paid = max(1, life_month - rule.amount)
            return add_months(event, first_paid - 1), first_paid - 1
    return None


def calculate_deadline(
    inp: DeadlineInput, *, today: date | None = None, rules: Rules | None = None
) -> DeadlineResult | ToolError:
    """Pure function: compute the due date and overdue status for one procedure."""
    rules = rules or load_rules()
    rule = rules.deadlines.get(inp.procedure)
    if rule is None:  # the YAML and the Literal disagree: a config bug, but still answer as data
        return ToolError(error=f"No deadline rule configured for {inp.procedure!r}.", needs=["procedure"])
    if not rule.covers(inp.event_date):
        return outside_window(rule, inp.event_date, f"the {inp.procedure} deadline")

    as_of = inp.as_of or today or date.today()
    due, recommended_by, direction = _due_date(rule, inp.event_date)
    caveats = [f"event_date was interpreted as the {EVENT_MEANING[inp.procedure]}."]

    match inp.procedure:
        case "anmeldung":
            caveats += [
                "If no Bürgerbüro appointment is available within 14 days, book the earliest slot and keep "
                "proof of the booking.",
                "Bring the landlord's confirmation (Wohnungsgeberbestätigung, § 19 BMG).",
                WEEKEND_CAVEAT,
            ]
        case "abmeldung":
            caveats += [
                "Deregistration is only required when moving abroad (no new address in Germany); it is possible "
                "at the earliest one week before moving out.",
                WEEKEND_CAVEAT,
            ]
        case "kindergeld_retroactive" | "elterngeld_retroactive":
            caveats.append("Apply as early as possible; the date shown is the last day without losing money.")
            paid = _paid_if_applied_on(rule, inp.event_date, as_of)
            if paid is not None and due is not None and as_of > due:
                unit = "month(s)" if inp.procedure == "kindergeld_retroactive" else "life month(s)"
                caveats.append(
                    f"The last day without losses has passed, but a late application still pays back: if it "
                    f"arrives on {as_of.isoformat()}, payment starts from {paid[0].isoformat()} and {paid[1]} "
                    f"{unit} are lost. Every further month of delay loses one more month, so apply now."
                )
            if inp.procedure == "elterngeld_retroactive" and inp.event_date.day > 28:
                caveats.append(
                    "For births on the 29th-31st the end of a life month can differ by a day; apply earlier."
                )
        case "residence_permit_extension":
            caveats += [
                "Apply at least 8 weeks before expiry. Processing at the Munich Ausländerbehörde can take up to "
                "7 months; a timely application keeps your current permit valid (Fiktionsbescheinigung).",
            ]
        case "rundfunkbeitrag_registration":
            fee_from = inp.event_date.replace(day=1)
            caveats.append(
                f"The fee is owed from {fee_from.isoformat()} (first day of the move-in month), "
                "even if you register later. Only one fee per flat."
            )
            caveats += [f"Pending change: {p.summary}" for p in rules.pending("rundfunkbeitrag")]

    paid_now = _paid_if_applied_on(rule, inp.event_date, as_of)
    return DeadlineResult(
        paid_from_if_applied_now=paid_now[0] if paid_now else None,
        months_lost_if_applied_now=paid_now[1] if paid_now else None,
        procedure=inp.procedure,
        event_date=inp.event_date,
        due_date=due,
        recommended_by=recommended_by,
        direction=direction,
        days_remaining=(due - as_of).days if due else None,
        is_overdue=due is not None and as_of > due,
        rule_text=rule.rule_text,
        consequences=rule.consequences,
        legal_basis=[rule.legal_basis],
        source_urls=[rule.source_url],
        rules_version=rules.version,
        caveats=caveats,
    )


calculate_deadline_tool = make_tool(
    name="calculate_deadline",
    description=(
        "Compute statutory deadlines: Anmeldung/Abmeldung (registering/deregistering an address), the last day "
        "to apply for Kindergeld or Elterngeld without losing retroactive months (and, if that day has passed, "
        "from which month a late application still pays and how many months are lost), when to apply for a residence "
        "permit extension, and Rundfunkbeitrag (TV licence) registration. Use whenever the user asks 'by when' "
        "or 'how long do I have' for one of these. Never compute these dates yourself."
    ),
    args_schema=DeadlineInput,
    fn=calculate_deadline,
)

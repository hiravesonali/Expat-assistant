"""`estimate_family_benefits`: Kindergeld (exact) and Basiselterngeld (simplified § 2 BEEG estimate).

Why "simplified": the Elterngeldstelle computes a standardised net income (Elterngeldnetto) from gross
pay, offsets Mutterschaftsgeld, and adds bonuses. We take the user's average net income as given and apply
only the § 2 replacement-rate slide plus min/max and the income cap. Every simplification is a caveat.
"""

import math
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from expat.schemas.profile import Citizenship, ResidenceStatus
from expat.tools._common import ToolError, ToolOutput, make_tool, outside_window
from expat.tools.rules import ElterngeldRule, Rules, load_rules

Eligibility = Literal["likely", "check", "unlikely"]

# Residence title -> (eligibility, note). Legal background: § 62 Abs. 2 EStG (Kindergeld) and § 1 Abs. 7
# BEEG (Elterngeld) use the same logic: settlement permits and most work-related titles qualify,
# education titles do not, and some other titles only under extra conditions.
_STATUS_ELIGIBILITY: dict[ResidenceStatus, tuple[Eligibility, str]] = {
    ResidenceStatus.EU_FREEDOM: ("likely", "EU/EEA/Swiss citizens with freedom of movement are eligible."),
    ResidenceStatus.BLUE_CARD: ("likely", "An EU Blue Card (§ 18g AufenthG) qualifies under § 62 Abs. 2 EStG."),
    ResidenceStatus.SETTLEMENT: ("likely", "A settlement permit (Niederlassungserlaubnis) qualifies."),
    ResidenceStatus.WORK_PERMIT: (
        "check",
        "Most residence permits for employment qualify, but some titles (e.g. certain seasonal or "
        "short-term titles) are excluded. Check your exact title.",
    ),
    ResidenceStatus.FAMILY_REUNION: (
        "check",
        "Family reunion permits usually qualify if they allow employment. Check your exact title.",
    ),
    ResidenceStatus.STUDENT: (
        "unlikely",
        "Residence permits for studies or training are generally excluded (§ 62 Abs. 2 Nr. 2 EStG).",
    ),
    ResidenceStatus.OTHER: ("check", "Eligibility depends on the exact residence title."),
    ResidenceStatus.UNKNOWN: (
        "check",
        "Residence status unknown: non-EU citizens need a qualifying residence title.",
    ),
}


class FamilyBenefitsInput(BaseModel):
    children_count: int = Field(ge=0, le=15, description="Number of children (incl. a newborn) in the household.")
    include_elterngeld: bool = Field(default=False, description="Also estimate Basiselterngeld for a (new) child.")
    child_birth_date: date | None = Field(
        default=None, description="(Expected) birth date of the child; required for Elterngeld."
    )
    avg_monthly_net_income_before_birth: float | None = Field(
        default=None, ge=0, description="Applicant's average monthly NET income in the 12 months before birth."
    )
    taxable_household_income_last_year: float | None = Field(
        default=None,
        ge=0,
        description="Taxable income (zu versteuerndes Einkommen) of both parents in the year before birth.",
    )
    citizenship: Citizenship | None = Field(default=None, description="Applicant's citizenship group.")
    residence_status: ResidenceStatus | None = Field(default=None, description="Applicant's residence title.")
    as_of: date | None = Field(default=None, description="Month the Kindergeld amount is needed for. Default: today.")


class FamilyBenefitsResult(ToolOutput):
    kindergeld_per_child_eur: float
    kindergeld_monthly_total_eur: float
    elterngeld_basis_monthly_estimate_eur: float | None
    elterngeld_replacement_rate: float | None
    elterngeld_months_basis: int | None
    eligible: Eligibility
    eligibility_notes: list[str]


def replacement_rate(net_income: float, rule: ElterngeldRule) -> float:
    """§ 2 Abs. 2 BEEG slide: +0.1 pp per FULL €2 below €1,000 (max 100 %), -0.1 pp per full €2 above €1,200
    (min 65 %). Between €1,000 and €1,200 the default 67 % applies.

    Rounded to 3 decimals so float noise (0.67 + 0.001 * 100 = 0.7700000000000001) never leaks into answers.
    """
    if net_income < rule.low_income_threshold_eur:
        steps = math.floor((rule.low_income_threshold_eur - net_income) / rule.slide_step_eur)
        rate = min(rule.max_replacement_rate, rule.replacement_rate_default + steps * rule.slide_step_rate)
    elif net_income > rule.high_income_threshold_eur:
        steps = math.floor((net_income - rule.high_income_threshold_eur) / rule.slide_step_eur)
        rate = max(rule.replacement_rate_high_income, rule.replacement_rate_default - steps * rule.slide_step_rate)
    else:
        rate = rule.replacement_rate_default
    return round(rate, 3)


def basiselterngeld(net_income: float, rule: ElterngeldRule) -> tuple[float, float]:
    """(monthly amount, rate): net income x rate, clamped to [min, max] (§ 2 Abs. 1 and 4 BEEG)."""
    rate = replacement_rate(net_income, rule)
    amount = min(rule.basis_max_eur, max(rule.basis_min_eur, net_income * rate))
    return round(amount, 2), rate


def _eligibility(citizenship: Citizenship | None, status: ResidenceStatus | None) -> tuple[Eligibility, str]:
    if citizenship in (Citizenship.GERMAN, Citizenship.EU):
        return "likely", "German and EU citizens living in Germany are eligible."
    return _STATUS_ELIGIBILITY[status or ResidenceStatus.UNKNOWN]


def estimate_family_benefits(
    inp: FamilyBenefitsInput, *, today: date | None = None, rules: Rules | None = None
) -> FamilyBenefitsResult | ToolError:
    """Pure function: Kindergeld total plus an optional Basiselterngeld estimate."""
    rules = rules or load_rules()
    kg, eg = rules.kindergeld, rules.elterngeld
    as_of = inp.as_of or today or date.today()
    if not kg.covers(as_of):
        return outside_window(kg, as_of, "Kindergeld")

    eligible, note = _eligibility(inp.citizenship, inp.residence_status)
    notes = [note]
    legal_basis = [kg.legal_basis, kg.eligibility_legal_basis]
    source_urls = [kg.source_url]
    caveats = [
        "Kindergeld is paid for children under 18 (under 25 while in education or training) who live in your "
        "household; apply at the Familienkasse.",
    ]
    if eligible != "likely":
        caveats.append("Eligibility depends on the residence title; confirm with the Familienkasse/Elterngeldstelle.")

    elterngeld_amount: float | None = None
    rate: float | None = None
    months: int | None = None
    if inp.include_elterngeld:
        birth, net_income = inp.child_birth_date, inp.avg_monthly_net_income_before_birth
        if birth is None or net_income is None:  # the `is None` checks also narrow the types for mypy
            needs = [] if birth is not None else ["child_birth_date"]
            needs += [] if net_income is not None else ["avg_monthly_net_income_before_birth"]
            return ToolError(error="The Elterngeld estimate needs more information.", needs=needs)
        if not eg.covers(birth):
            return outside_window(eg, birth, "Elterngeld (income cap and amounts)")

        legal_basis += [eg.legal_basis, eg.eligibility_legal_basis]
        source_urls.append(eg.source_url)
        income_cap_exceeded = (
            inp.taxable_household_income_last_year is not None
            and inp.taxable_household_income_last_year > eg.income_cap_taxable_eur
        )
        if income_cap_exceeded:
            elterngeld_amount, months = 0.0, 0
            notes.append(
                f"No Elterngeld: taxable household income above €{eg.income_cap_taxable_eur:,.0f} in the year "
                "before birth (§ 1 Abs. 8 BEEG)."
            )
        else:
            elterngeld_amount, rate = basiselterngeld(net_income, eg)
            months = eg.months_basis + eg.partner_months
            if inp.taxable_household_income_last_year is None:
                caveats.append(
                    f"Income cap not checked: Elterngeld is excluded if the parents' taxable income in the year "
                    f"before birth exceeded €{eg.income_cap_taxable_eur:,.0f}."
                )
        caveats += [
            "Simplified estimate: the Elterngeldstelle uses a standardised net income derived from gross pay, "
            "so the real amount can differ.",
            "Mutterschaftsgeld and the employer top-up after birth are offset against Elterngeld (not included).",
            "Sibling bonus (Geschwisterbonus) and multiple-birth supplement are not included.",
            f"Basiselterngeld runs {eg.months_basis} months for one parent; {eg.partner_months} extra partner "
            "months if both parents take time off and lose income. ElterngeldPlus is not covered.",
        ]
        caveats += [
            f"Pending change: {p.summary}"
            for p in rules.pending("elterngeld")
            if p.affects_from is not None and birth >= p.affects_from
        ]

    return FamilyBenefitsResult(
        kindergeld_per_child_eur=kg.amount_per_child_eur,
        kindergeld_monthly_total_eur=round(kg.amount_per_child_eur * inp.children_count, 2),
        elterngeld_basis_monthly_estimate_eur=elterngeld_amount,
        elterngeld_replacement_rate=rate,
        elterngeld_months_basis=months,
        eligible=eligible,
        eligibility_notes=notes,
        legal_basis=legal_basis,
        source_urls=source_urls,
        rules_version=rules.version,
        caveats=caveats,
    )


estimate_family_benefits_tool = make_tool(
    name="estimate_family_benefits",
    description=(
        "Compute Kindergeld (child benefit, exact monthly amount) and optionally estimate Basiselterngeld "
        "(parental allowance) from net income, including eligibility by residence status and the income cap. "
        "Use whenever the user asks how much Kindergeld or Elterngeld they get or whether they are eligible. "
        "Never compute these amounts yourself. Ask for missing inputs (birth date, net income)."
    ),
    args_schema=FamilyBenefitsInput,
    fn=estimate_family_benefits,
)

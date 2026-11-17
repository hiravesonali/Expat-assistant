"""Typed, validated loader for the versioned rules file (`rules/2026.yaml`).

Why a Pydantic model instead of reading raw YAML dicts in each tool:
- A typo in the YAML (missing `legal_basis`, a string where a number belongs) fails loudly at load time,
  not as a wrong answer in production. Think of it as zod-parsing a JSON config at startup.
- Every rule shares `RuleMeta` (legal basis, URL, validity window, last_verified), so "every tool output is
  citable" and "refuse dates outside the validity window" are enforced in one place.
"""

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from expat.config import REPO_ROOT

DEFAULT_RULES_PATH = REPO_ROOT / "rules" / "2026.yaml"


class RuleMeta(BaseModel):
    """Provenance shared by every rule. `valid_until=None` means the current law has no end date."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    legal_basis: str
    source_url: str
    valid_from: date | None = None
    valid_until: date | None = None
    last_verified: date

    def covers(self, day: date) -> bool:
        """True if `day` lies inside the validity window (both ends inclusive)."""
        if self.valid_from is not None and day < self.valid_from:
            return False
        return self.valid_until is None or day <= self.valid_until

    def window_text(self) -> str:
        """Human-readable window for error messages, e.g. '2026-01-01 to open-ended'."""
        start = self.valid_from.isoformat() if self.valid_from else "open"
        end = self.valid_until.isoformat() if self.valid_until else "open-ended"
        return f"{start} to {end}"


class LandlordTier(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    min_years: int = Field(ge=0)
    months: int = Field(gt=0)


class TenancyNoticeRule(RuleMeta):
    tenant_months: int
    landlord_months: list[LandlordTier]
    grace_working_days: int
    saturday_is_working_day: bool

    @model_validator(mode="after")
    def _tiers_sorted(self) -> "TenancyNoticeRule":
        """The lookup picks the last tier with min_years <= duration, which only works if sorted."""
        years = [t.min_years for t in self.landlord_months]
        if not years or years != sorted(years) or years[0] != 0:
            raise ValueError("landlord_months must be sorted ascending by min_years and start at 0")
        return self


class TenancyMunichRule(RuleMeta):
    kappungsgrenze_pct: int
    mietpreisbremse_active: bool


class KindergeldRule(RuleMeta):
    amount_per_child_eur: float
    max_children: int
    eligibility_legal_basis: str


class ElterngeldRule(RuleMeta):
    basis_min_eur: float
    basis_max_eur: float
    replacement_rate_default: float
    replacement_rate_high_income: float
    low_income_threshold_eur: float
    high_income_threshold_eur: float
    slide_step_eur: float
    slide_step_rate: float
    max_replacement_rate: float
    income_cap_taxable_eur: float
    months_basis: int
    partner_months: int
    eligibility_legal_basis: str


class BlueCardRule(RuleMeta):
    min_salary_standard_eur: float
    min_salary_shortage_eur: float


class RundfunkbeitragRule(RuleMeta):
    monthly_eur: float


class SchengenRule(RuleMeta):
    max_days: int
    window_days: int
    resident_legal_basis: str


DeadlineKind = Literal[
    "days_after",  # due = event + N days (Anmeldung)
    "calendar_months_retroactive",  # paid back N calendar months before the application month (Kindergeld)
    "life_months_retroactive",  # paid back N life months of the child (Elterngeld)
    "before_expiry",  # apply before event date; N = recommended lead time in days
    "without_undue_delay",  # "unverzüglich": no fixed number of days
]


class DeadlineRule(RuleMeta):
    kind: DeadlineKind
    amount: int = Field(ge=0)
    rule_text: str
    consequences: str | None = None


class PendingChange(BaseModel):
    """An announced change that is NOT law yet. Tools only mention it as a caveat."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    topic: str
    summary: str
    affects_from: date | None
    status: Literal["cabinet_approved", "proposed", "in_parliament", "debate"]
    source_url: str
    last_verified: date


class Rules(BaseModel):
    """The whole rules file. `extra="forbid"` catches misspelt top-level keys."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    last_verified: date
    tenancy_notice: TenancyNoticeRule
    tenancy_munich: TenancyMunichRule
    kindergeld: KindergeldRule
    elterngeld: ElterngeldRule
    blue_card: BlueCardRule
    rundfunkbeitrag: RundfunkbeitragRule
    schengen: SchengenRule
    deadlines: dict[str, DeadlineRule]
    pending_changes: list[PendingChange] = Field(default_factory=list)

    def pending(self, topic: str) -> list[PendingChange]:
        """Pending changes for one topic (e.g. 'elterngeld'), for caveats."""
        return [p for p in self.pending_changes if p.topic == topic]


@lru_cache
def load_rules(path: Path = DEFAULT_RULES_PATH) -> Rules:
    """Parse and validate the rules file once per process.

    `lru_cache` makes this a lazy singleton (like a memoised module-level promise in TS). Tests can pass
    another path, or call `load_rules.cache_clear()` after editing the file.
    """
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Rules.model_validate(raw)

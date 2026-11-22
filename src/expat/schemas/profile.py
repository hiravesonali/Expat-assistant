"""User profile: coarse enums only, no PII (see ADR-0007).

Stored only in the Streamlit session (st.session_state); never persisted server-side.
"""

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class Citizenship(StrEnum):
    EU = "eu"
    NON_EU = "non_eu"
    GERMAN = "german"
    UNKNOWN = "unknown"


class ResidenceStatus(StrEnum):
    BLUE_CARD = "blue_card"
    WORK_PERMIT = "work_permit"
    STUDENT = "student"
    FAMILY_REUNION = "family_reunion"
    SETTLEMENT = "settlement"
    EU_FREEDOM = "eu_freedom"
    OTHER = "other"
    UNKNOWN = "unknown"


class Employment(StrEnum):
    EMPLOYEE = "employee"
    FREELANCER = "freelancer"
    SELF_EMPLOYED = "self_employed"
    STUDENT = "student"
    UNEMPLOYED = "unemployed"
    UNKNOWN = "unknown"


class FamilyStatus(StrEnum):
    SINGLE = "single"
    MARRIED = "married"
    PARTNERSHIP = "partnership"
    UNKNOWN = "unknown"


class Housing(StrEnum):
    RENTING = "renting"
    OWNING = "owning"
    LOOKING = "looking"
    UNKNOWN = "unknown"


class UserProfile(BaseModel):
    # Where the user lives. None = unknown (the assistant asks when the answer depends on it). `city` is a
    # chunk-metadata slug for supported cities ("berlin", "cologne"; see expat.places) or a free name.
    city: str | None = None
    state: str | None = None  # state code, e.g. "BE"
    citizenship: Citizenship = Citizenship.UNKNOWN
    residence_status: ResidenceStatus = ResidenceStatus.UNKNOWN
    employment: Employment = Employment.UNKNOWN
    family_status: FamilyStatus = FamilyStatus.UNKNOWN
    children_count: int = Field(default=0, ge=0, le=10)
    youngest_child_age: int | None = Field(default=None, ge=0, le=25)
    housing: Housing = Housing.UNKNOWN
    # Set by the app's language switch (English | Deutsch). None = answer in the language of the question
    # (evals, API callers without a preference).
    answer_language: str | None = Field(default=None, pattern=r"^(en|de)$")

    @model_validator(mode="after")
    def _normalise_location(self) -> "UserProfile":
        """Slugs lower-case, state codes upper-case; a supported city implies its state."""
        from expat.places import state_for_city  # local import: places has no deps, avoids import cycles

        self.city = self.city.strip().lower() or None if self.city else None
        self.state = self.state.strip().upper() or None if self.state else None
        if self.city and (implied := state_for_city(self.city)):
            self.state = implied
        return self

    def summary(self) -> str:
        """Compact one-line description for the system prompt."""
        parts: list[str] = []
        if self.citizenship != Citizenship.UNKNOWN:
            parts.append(
                self.citizenship.value.replace("_", "-").upper()
                if self.citizenship != Citizenship.GERMAN
                else "German citizen"
            )
        if self.residence_status != ResidenceStatus.UNKNOWN:
            parts.append(f"residence: {self.residence_status.value.replace('_', ' ')}")
        if self.employment != Employment.UNKNOWN:
            parts.append(self.employment.value.replace("_", "-"))
        if self.family_status != FamilyStatus.UNKNOWN:
            parts.append(self.family_status.value)
        if self.children_count:
            kids = f"{self.children_count} child{'ren' if self.children_count > 1 else ''}"
            if self.youngest_child_age is not None:
                kids += f" (youngest {self.youngest_child_age})"
            parts.append(kids)
        if self.housing != Housing.UNKNOWN:
            parts.append(self.housing.value)
        if self.city or self.state:
            from expat.places import STATES, city_label

            where = city_label(self.city) if self.city else STATES.get(self.state or "", self.state or "")
            parts.append(f"lives in {where}" + (f" ({self.state})" if self.city and self.state else ""))
        else:
            parts.append("location unknown")
        return "User: " + ", ".join(parts) + "."

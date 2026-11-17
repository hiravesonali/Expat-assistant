"""User profile: coarse enums only, no PII (see ADR-0007).

Stored only in the Streamlit session (st.session_state); never persisted server-side.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


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
    city: str = "munich"
    state: str = "BY"
    citizenship: Citizenship = Citizenship.UNKNOWN
    residence_status: ResidenceStatus = ResidenceStatus.UNKNOWN
    employment: Employment = Employment.UNKNOWN
    family_status: FamilyStatus = FamilyStatus.UNKNOWN
    children_count: int = Field(default=0, ge=0, le=10)
    youngest_child_age: int | None = Field(default=None, ge=0, le=25)
    housing: Housing = Housing.UNKNOWN
    answer_language: str = Field(default="en", pattern=r"^(en|de)$")

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
        parts.append(f"lives in {self.city.title()} ({self.state})")
        return "User: " + ", ".join(parts) + "."

# Tool Specifications

> Course requirement: **tool calling for practical tasks** ✅ (required).
> Schemas are described in Pydantic style. They are not implemented yet.

## Design principles (defend these in the review)

1. **Deterministic maths lives in code, never in the LLM.** LLMs are bad at date arithmetic and "the 3rd working day of the month". Tools are pure Python functions with unit tests.
2. **Amounts and thresholds come from `rules/2026.yaml`, never from code or the prompt.** Each value carries `source_url`, `legal_basis`, `valid_from`, `valid_until` and `last_verified`. A yearly update means editing YAML, and tools refuse to answer for dates outside a rule's validity window.
3. **Every tool output is citable.** Each result contains `legal_basis` + `source_url` + `rules_version`, and the answer cites tool results just like retrieved chunks (`[T1]`).
4. **Tools return `caveats[]`.** These are simplifications the LLM must surface ("Elterngeld estimate ignores Mutterschaftsgeld offsets").
5. **Validation errors are data, not exceptions.** Bad input returns `{"error": "...", "needs": ["move_in_date"]}` so the LLM can ask the user a follow-up question.

## Example `rules/2026.yaml` (values verified 2026-11-17)

```yaml
kindergeld:
  amount_per_child_eur: 259
  valid_from: 2026-01-01
  legal_basis: "§ 66 EStG"
  source_url: https://familienportal.de/bmbfsfj/themen/familie/familienleistungen/kindergeld/kindergeld-73892
  last_verified: 2026-11-17
elterngeld:
  basis_min_eur: 300
  basis_max_eur: 1800
  replacement_rate_default: 0.67      # 0.65 above €1,240 net; up to 1.00 below €1,000 net (sliding)
  income_cap_taxable_eur: 175000      # births from 2025-04-01
  legal_basis: "§ 2 BEEG, § 1 Abs. 8 BEEG"
  source_url: https://www.gesetze-im-internet.de/beeg/__2.html
  note: "A reform (€330/€1,900) was approved by the cabinet in Nov 2026 for births from 2027-11-01 and is NOT law yet. Re-check."
blue_card:
  min_salary_standard_eur: 50700
  min_salary_shortage_eur: 45934.20
  valid_for_year: 2026
tenancy_munich:
  kappungsgrenze_pct: 15              # Bavarian Mieterschutzverordnung, 2026-01-01..2029-12-31
  mietpreisbremse_active: true
  mietpreisbremse_valid_until: 2029-12-31
  source_url: https://www.verkuendung-bayern.de/baymbl/2025-558/
rundfunkbeitrag:
  monthly_eur: 18.36
  note: "KEF proposed €18.64 from 2027 (not decided); BVerfG case pending. Re-check in Jan 2027."
anmeldung:
  deadline_days: 14
  legal_basis: "§ 17 Abs. 1 BMG"
```

## MVP tools (priority order)

### 1. `calculate_tenancy_notice` ⭐ MVP
**Purpose:** compute the last day the notice must arrive, and the tenancy end date, for a tenant or a landlord.
**Data source:** § 573c BGB (rules), the `holidays` package (subdivision `BY` for Bavarian public holidays).

```text
Input  NoticeInput
  party: Literal["tenant", "landlord"]
  tenancy_start: date                 # to compute duration (landlord: 3 / 6 / 9 months)
  notice_date: date | None = today    # date the letter will be *received*
  contract_type: Literal["unlimited", "fixed_term", "furnished_room_in_landlord_flat"] = "unlimited"
  state: str = "BY"

Output NoticeResult
  notice_period_months: int           # 3 / 6 / 9
  receipt_deadline_this_month: date   # 3rd working day of the current month
  received_in_time_for_this_month: bool
  tenancy_end_date: date
  legal_basis: "§ 573c Abs. 1 BGB"
  source_url, rules_version
  caveats: list[str]                  # e.g. "Landlord also needs a legitimate interest (§ 573 BGB)"
```
**Edge cases:** Saturdays do **not** count as working days for the 3-day grace period (BGH VIII ZR 291/09). Public holidays in Bavaria. Notice received after the 3rd working day shifts the end date by a month. Fixed-term contracts and a contractual *Kündigungsverzicht* (waiver, usually ≤ 4 years) → caveat and no calculation. Furnished rooms inside the landlord's flat have shorter periods (§ 573c (3)), so return a caveat. The written form requirement (§ 568 BGB: a signed letter, not email) is always included as a caveat.

### 2. `calculate_deadline` ⭐ MVP
**Purpose:** generic statutory deadlines for procedures in the corpus.
**Data source:** `rules/2026.yaml` → `deadlines:` registry (each with a legal basis).

```text
Input  DeadlineInput
  procedure: Literal["anmeldung", "abmeldung", "kindergeld_retroactive", "elterngeld_retroactive",
                     "residence_permit_extension", "rundfunkbeitrag_registration"]
  event_date: date                    # move-in date, birth date, permit expiry...

Output DeadlineResult
  procedure, due_date: date | None, direction: Literal["before", "after", "within"]
  days_remaining: int | None, is_overdue: bool
  rule_text: str                      # "within two weeks after moving in"
  legal_basis, source_url, consequences: str | None   # e.g. fine (Bußgeld) for late Anmeldung
  paid_from_if_applied_now: date | None   # Kindergeld / Elterngeld only: a late application still pays back
  months_lost_if_applied_now: int | None
  caveats: list[str]
```
**Edge cases:** Kindergeld/Elterngeld are paid retroactively for only **6 / 3 months** before the application month (§ 70 Abs. 1 Satz 2 EStG, § 7 Abs. 1 Satz 2 BEEG). Past the last loss-free day the tool says from which month an application today is still paid, so a late family is told "apply now, you still get 6 months", not "too late" (golden `fam-004`). Residence permit extensions should be applied for before expiry (Munich processing time can be up to 7 months, so the tool suggests applying early, as a caveat). If Bürgeramt appointments are unavailable within 14 days, the caveat says to book the earliest slot and keep proof.

### 3. `estimate_family_benefits` ⭐ MVP
**Purpose:** Kindergeld (exact) and Basiselterngeld (simplified estimate).

```text
Input  FamilyBenefitsInput
  children_count: int (0..15)
  include_elterngeld: bool = False
  child_birth_date: date | None              # needed for Elterngeld rules (cap applies to births ≥ 2025-04-01)
  avg_monthly_net_income_before_birth: float | None
  taxable_household_income_last_year: float | None   # for the €175k cap
  residence_status: str | None               # Kindergeld eligibility for non-EU depends on the title (Blue Card: yes)

Output FamilyBenefitsResult
  kindergeld_monthly_total_eur: float
  kindergeld_per_child_eur: float
  elterngeld_basis_monthly_estimate_eur: float | None
  elterngeld_months_basis: int | None        # 12 + 2 partner months
  eligible: Literal["likely", "check", "unlikely"], eligibility_notes: list[str]
  legal_basis: list[str], source_urls, rules_version, caveats
```
**Edge cases:** income above the cap means no Elterngeld. The replacement-rate slide below €1,000 and above €1,200 net. ElterngeldPlus is out of scope for the MVP (caveat). Non-EU eligibility depends on the residence title (§ 62 EStG / § 1 (7) BEEG). Blue Card holders qualify, but some titles don't, so the result becomes `check` + a link. The pending reform appears as a caveat if `child_birth_date ≥ 2027-11-01`.

### 4. `generate_document_checklist` ⭐ MVP (structured output + RAG)
**Purpose:** a personalised list of documents for a procedure, **grounded in retrieved checklist chunks**. This is the one tool that is itself an LLM call: a structured-output chain over retrieved `source_type=checklist` chunks. It shows the course's "structured output" pattern explicitly.

```text
Input  ChecklistInput
  procedure: Literal["anmeldung", "blue_card_first_permit", "blue_card_extension", "settlement_permit_blue_card",
                     "kindergeld_application", "elterngeld_application", "kita_registration"]
  profile: UserProfile                       # injected server-side, not chosen by the LLM

Output Checklist
  procedure, city: "munich"
  items: list[ChecklistItem]
    ChecklistItem: name_en, name_de, required: bool, applies_because: str | None,
                   notes: str | None, source_chunk_id: str      # every item must point to a chunk
  fees: list[{label, amount_eur, source_chunk_id}]
  steps: list[{order, description, source_chunk_id}]
  missing_info: list[str]
```
**Edge cases:** items without a `source_chunk_id` are **dropped** by a validator, which prevents hallucinated documents. Family Anmeldung uses the family variant page. If no checklist chunk is retrieved for the procedure, return `missing_info` and point to the official page.

### 5. `schengen_days_calculator` (MVP, cuttable)
**Purpose:** rolling 90/180 calculation. Main use case: **visiting parents** (non-EU) of the Blue Card family.

```text
Input  SchengenInput
  stays: list[{entry: date, exit: date}]     # past + planned
  check_date: date = today
  traveller: Literal["visitor_short_stay", "resident_permit_holder"]

Output SchengenResult
  days_used_in_window: int, days_remaining: int
  window_start: date, window_end: date
  latest_allowed_exit_for_planned_stay: date | None
  overstay: bool, source_url (EU Commission calculator), caveats
```
**Edge cases:** entry and exit days both count. Holders of a German residence permit are not subject to the rule for stays in Germany, so the tool returns an explanation instead of a count (travel to *other* Schengen states is still limited, Art. 21 CISA → caveat, medium confidence). Overlapping or invalid date ranges are rejected.

## Stretch tools

| Tool | Purpose | Why stretch |
|---|---|---|
| `check_rent_increase` | Munich Kappungsgrenze (15% in 3 years, BY regulation until 2029-12-31), 15-month/12-month waiting periods (§ 558 (1) BGB), consent deadline (§ 558b) | Feasible. Comparing against the Mietspiegel needs the city calculator, so the tool only checks the formal limits and links the Mietspiegel. **Best stretch tool for the persona.** |
| `draft_letter` | Kündigung (tenant notice) or Widerspruch, in German with an English explanation, as structured output + template | Easy, but needs careful caveats. A great demo. |
| `find_office` | Munich KVR/Bürgerbüro/Ausländerbehörde address + booking link (static JSON) | Low technical value |
| `check_mietpreisbremse` | New-let rent vs Mietspiegel +10% with § 556e/f exceptions | Needs Mietspiegel inputs (location, year, size, features). Too complex for the MVP. Explain the limitation instead. |
| Net salary | **Don't build a tax engine.** Link to or call the official BMF Lohnsteuer calculator (it has an XML interface) and label the result an estimate | Scope + liability |

## Retrieve vs tool: how the model decides

```
User question
   │
   ▼
QueryAnalysis (structured output) ── intent ∈ {info, calculation, checklist, mixed, out_of_scope}
   │
   ├─ out_of_scope/sensitive → safety policy (no retrieval, redirect)
   │
   ├─ ALWAYS retrieve (except out_of_scope): even calculations need legal context to explain the result
   │
   ▼
Answer agent (tool-calling model; retrieved context in the prompt; tools bound)
   • Tool descriptions say WHEN to use each tool ("Use whenever the user asks for a date or number of months…")
   • System rule: "Never compute dates, amounts or periods yourself. If a number is needed and no tool covers it, quote it
     only if it appears verbatim in the context; otherwise say you can't confirm it."
   • The agent can call tools 0..n times (max 4 iterations), then writes the answer citing [S#] chunks and [T#] tool results.
   • Missing tool inputs → ask the user (e.g. "When did your tenancy start?") instead of guessing.
```

**Why "always retrieve + agentic tools" rather than a pure agent that decides whether to retrieve:**
retrieval quality is what we evaluate. A deterministic retrieval stage makes the ablations reproducible and the step visualisation consistent. The model still decides *autonomously* about tools, and a `search_knowledge` tool (stretch) lets it fetch more context in a follow-up. In **Sprint 3** this becomes a full agent where retrieval is just another tool. Mention this evolution in the review.

**How tools and RAG combine in one answer:** example for "I've rented my flat in Munich for 6 years. If my landlord gives notice today, when do I have to leave?"
1. Retrieval returns § 573c BGB [S1] and § 573 BGB (legitimate interest) [S2].
2. The agent calls `calculate_tenancy_notice(party="landlord", tenancy_start=…, notice_date=today)` → [T1].
3. Answer: "The notice period is 6 months [S1][T1], so your tenancy would end on 31 May 2027 [T1]. Note the landlord needs a legitimate interest such as personal need [S2]…" plus the disclaimer.

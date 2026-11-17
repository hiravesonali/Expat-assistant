# ADR-0007: Stateless backend; profile and history live in the browser

- **Status:** Proposed
- **Context:** Personalisation needs a profile (residence status, family, city), which is personal data under GDPR. A conversation sidebar needs history. Adding a database, authentication and deletion flows would be a lot of scope.

## Options
1. Server-side persistence (Postgres/SQLite + auth).
2. **Browser-only storage (localStorage/IndexedDB), sent with each request.**
3. No persistence at all.

## Decision
Option 2. The profile holds coarse enums only: no name, address, birth date, passport or income.

## Rationale
- Data minimisation and privacy by design: the server stores nothing personal, so there is nothing to breach or delete.
- The MVP needs no authentication.
- In traces, the profile is attached as LangSmith run metadata (non-identifying enums). We use the LangSmith EU region and can hide inputs for public demos.

## Consequences
- History doesn't sync across devices, which is acceptable for the MVP.
- Request payloads grow with history, so we cap it at 6 turns plus a token budget.
- Production path: add accounts and server-side storage with consent and a retention policy (Sprint 3+ material).

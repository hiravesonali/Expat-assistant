# Golden dataset v1

`golden_v1.jsonl` contains 40 hand-written questions for the Expat Germany Assistant. Each line is one JSON object,
validated by `expat.evals.dataset.GoldenExample`; `tests/evals/test_dataset.py` validates the whole file in CI.

## Composition

| Slice | # | dev / holdout | Notes |
|---|---|---|---|
| bureaucracy (`bur-*`) | 11 | 8 / 3 | Anmeldung, Abmeldung, Blue Card, settlement permit, Rundfunkbeitrag |
| tenancy (`ten-*`) | 11 | 8 / 3 | notice, deposit, Kappungsgrenze, Mietpreisbremse, Nebenkosten, Minderung, subletting |
| family (`fam-*`) | 9 | 6 / 3 | Kindergeld, Elterngeld, Kita |
| multi_domain (`mul-*`) | 4 | 3 / 1 | tests decomposition |
| out_of_scope (`oos-*`) | 5 | 3 / 2 | asylum, tax filing, criminal law, eviction lawsuit, medical; `should_refuse: true` |
| **total** | **40** | **28 / 12** | |

Cross-cutting: 8 German-language questions (spread over all five slices, 3 of them in the holdout split),
11 questions with an `expected_tool`. Most profiles are the core persona (non-EU Blue Card holder, married, two
children, renting in Munich); variants cover an EU citizen, a non-EU student, a non-EU freelancer and a settled
long-term resident. Questions are written the way users really ask: vague, with English approximations of German terms
("registration thing", "kinder money", "TV tax thing").

## Fields

| Field | Meaning |
|---|---|
| `id` | `<slice-prefix>-NNN`, stable forever (results are joined on it) |
| `split` | `dev` (tune on this) or `holdout` (report only, never tune on it) |
| `question`, `language` | the user message and its language (`en` / `de`) |
| `profile` | a `expat.schemas.UserProfile` (enums only) |
| `domains`, `category` | `category` ∈ single_domain, multi_domain, numeric, tool, legal_lookup, out_of_scope, sensitive |
| `expected_sources` | `doc_key`s matched with `expat.schemas.doc_key_matches` (see `docs/conventions.md`): `bgb#573c` matches only that §, a bare `muc-anmeldung` matches any section of that page. `required: true` keys count for hit@k / recall@k / MRR; optional keys only count as "correct" citations |
| `expected_tool` | `{name, args_subset}` or `null` (= no tool should be called). Args are compared as a subset; dates as ISO strings |
| `reference_answer` | ground truth for the correctness judge |
| `must_include` / `must_not_include` | cheap deterministic string checks, case-insensitive. `a\|b\|c` means "any of these alternatives" (e.g. `2 weeks\|two weeks\|14 days`) |
| `should_refuse` | out-of-scope / sensitive: the answer must redirect (lawyer, Mieterverein, doctor, …) instead of advising. These have no expected sources and are skipped by the retrieval metrics |

## How the questions were verified

1. Every amount, threshold and period matches `docs/tools.md` / `rules/2026.yaml` (Kindergeld €259, Elterngeld
   €300–1,800 and the €175k cap, Blue Card €50,700 / €45,934.20, Rundfunkbeitrag €18.36, Anmeldung within two weeks,
   landlord notice 3/6/9 months, Munich Kappungsgrenze 15%).
2. The § numbers were checked against gesetze-im-internet.de on 2026-11-17, in particular § 18g (1)/(4) and § 18c (2)
   AufenthG (27 / 21 months), § 30 (1) S. 3 Nr. 5 AufenthG (no German needed for spouses of Blue Card holders),
   § 66 (1) EStG (€259), § 7 (1) BEEG (3 months retroactive), § 4 (3)/(6) BEEG (12+2 months, parallel receipt in one
   month only). Note: the 6-month Kindergeld retroactivity is § 70 (1) EStG, not § 66.
3. Web-page sources use the bare `source_id` from `docs/conventions.md` so they survive re-chunking. The test suite
   checks every `doc_key` against that table (or the `<law>#<paragraph>` pattern).

When a fact changes (e.g. the Elterngeld reform for births from 2027-11-01), create `golden_v2.jsonl` rather than editing
v1, so old experiment results stay comparable.

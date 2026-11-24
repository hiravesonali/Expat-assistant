# Judge calibration result (correctness judge, google/gemini-2.5-flash-lite)

Reference labels by: **Claude Opus 5.5 (an LLM); items 2-4 (fam-006, bur-006, ten-005) reviewed and confirmed by a human**

- Agreement with the reference label: **14/15** (93%), Cohen's kappa **0.81**
- Reference 'correct' rate 73%, judge 'correct' rate 80%
- Judge too strict (reference yes, judge no): none
- Judge too lenient (reference no, judge yes): fam-005

Sample: all judge fails + random judge passes (seed 7), so the sample is enriched for failures and
the agreement here is a conservative estimate for the full run.

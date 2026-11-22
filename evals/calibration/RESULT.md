# Judge calibration result (correctness judge, claude-haiku-4.5)

Reference labels by: **Claude Opus 5.5 (an LLM); items 2-4 (fam-006, bur-006, ten-005) reviewed and confirmed by a human**

- Agreement with the reference label: **12/15** (80%), Cohen's kappa **0.44**
- Reference 'correct' rate 73%, judge 'correct' rate 80%
- Judge too strict (reference yes, judge no): fam-006
- Judge too lenient (reference no, judge yes): fam-004, bur-004

Sample: all judge fails + random judge passes (seed 7), so the sample is enriched for failures and
the agreement here is a conservative estimate for the full run.

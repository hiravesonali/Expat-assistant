# Judge calibration result (correctness judge, claude-haiku-4.5)

Reference labels by: **Claude Opus 5.5 (an LLM, not a human): a second-model check; human review of the 3 disagreements pending**

- Agreement with the reference label: **12/15** (80%), Cohen's kappa **0.44**
- Reference 'correct' rate 73%, judge 'correct' rate 80%
- Judge too strict (reference yes, judge no): fam-006
- Judge too lenient (reference no, judge yes): fam-004, bur-004

Sample: all judge fails + random judge passes (seed 7), so the sample is enriched for failures and
the agreement here is a conservative estimate for the full run.

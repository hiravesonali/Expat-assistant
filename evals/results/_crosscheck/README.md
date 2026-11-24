# Cross-check runs, kept out of the report

`REPORT.md` shows the latest run per variant. These runs use a different judge from the headline numbers
(Claude Haiku 4.5, 2026-11-23), so mixing them into the report would compare R0 and R5 under different judges.

- `answers-R5-holdout-20261124T145356Z.json`: holdout R5 (32 questions), judge `google/gemini-2.5-flash-lite`,
  run with `--samples` as the input for the Ragas cross-check (`evals/results/ragas/`). Correctness 0.93,
  groundedness 0.96, citation validity 1.00 (new answers, so not directly comparable with the Haiku run).

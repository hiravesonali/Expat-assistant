# Subset runs (`--ids`), kept out of the report

- `answers-R5-dev-20261123T103842Z.json`: 10 dev questions after the location_dependent prompt fix
  (58996b2): bur-031 no longer asks for the city; bur-001 / bur-012 still resolve it.
- `answers-R5-holdout-20261124T145138Z.json`: started without `--dataset expat-golden-v4`, so it used the old
  default LangSmith dataset and ran only 12 of 32 holdout questions. Replaced by the full run in `_crosscheck/`.

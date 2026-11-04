---
name: new-metric
description: Add a new scouting metric end to end (SQL, definition, test, report section) so it passes make check
---

# Add a new metric

1. **Define it.** Add a bullet to the "Definitions" docstring at the top of `scout/metrics.py`:
   name, formula, and which events count.
2. **Compute it.** Add a function to `scout/metrics.py` with the signature
   `def <name>(con, team_id, as_of, season_types=(2, 3))`. Filter games with `_games(as_of, season_types)`.
   Return plain dicts or a DataFrame. SQL only; no pandas loops over play-by-play.
3. **Test it.** Add a test in `tests/` that runs the function on `tests/fixtures/good/`
   (point a connection at the fixture folder) and asserts a hand-checked value or a sane range.
4. **Report it.** In `scout/report.py` `compute()`, add a section. Print every value with
   `L.num("<section>.<field>", value)`; ranks with `L.rank`; names with `L.text`.
   If the metric suggests a defensive adjustment, add a candidate to `guard_keys` with a score.
5. **Verify.** `make check` (validate + tests + build ATL report + check-report). Open the new
   report and read the section as a coach would.

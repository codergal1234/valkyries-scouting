# AGENTS.md

Opponent scouting reports for the Golden State Valkyries, built from public WNBA data
(ESPN via SportsDataverse). Python 3.11+, DuckDB, no web framework.

## Commands

| What | Command |
|---|---|
| Install (creates `.venv/`, installs pinned deps) | `make setup` |
| Lint + format check (ruff) | `make lint` (auto-fix: `make format`) |
| Type check (mypy strict) | `make typecheck` |
| Git hooks on all files (large files, gitleaks, ruff, mypy) | `make hooks` |
| Download + rebuild clean tables | `make ingest` |
| Run all data checks | `make validate` |
| Unit tests + coverage gate (after `make ingest`) | `make test` |
| Build a report | `make report OPP=ATL` (optional `ASOF=2026-10-29`) |
| Check report numbers | `make check-report` |
| Everything a PR must pass | `make check` |

Every target runs `.venv/bin/python`. Override with `PY=`, e.g. `make check PY=/path/to/python`.
Dependencies are pinned with `==` in `requirements.txt`; change a version there, never install ad hoc.

`make check` must pass before you open a PR. If it fails, fix the cause, not the check.

## Layout

- `scout/ingest.py`: downloads raw files, writes `data/clean/`. Upstream renames go in `COLUMN_ALIASES`.
- `scout/contracts.py`: required columns and types per table.
- `scout/validate.py`: contract checks + basketball invariants (points must add up).
- `scout/db.py`: typed helpers for DuckDB results (`scalar`, `records`).
- `scout/metrics.py`: every metric, in SQL. Definitions at the top of the file.
- `scout/report.py`: builds the report. All numbers go through `Ledger`.
- `scout/check_report.py`: proves every number in a report was computed.
- `tests/`: pytest, runs on the small fixture in `tests/fixtures/good/`.
- `docs/requests/`: staff requests, one file each.

## Code style

- ruff enforces style, imports, pep8 naming (snake_case functions and variables, CapWords classes)
  and a max cyclomatic complexity of 10. Config is in `pyproject.toml`. Lines up to 120 chars.
- `make setup` installs pre-commit hooks (`.pre-commit-config.yaml`). Commits are blocked on files over
  500 KB, secrets found by gitleaks, ruff errors or mypy errors. Never bypass them with `--no-verify`.
- Tests live in `tests/test_*.py` and test functions are named `test_*` (set in `pyproject.toml`).
  `make test` prints the 10 slowest tests and fails if line coverage of `scout/` drops below
  `fail_under` in `pyproject.toml`. Raise that number when you add tests; never lower it.
- mypy runs in strict mode: every function needs parameter and return annotations.
  Use `scout.db.scalar` / `scout.db.records` to read query results with types.

## Rules

1. Never write to `data/raw/`. It is exactly what upstream served. A hook blocks it.
2. Never weaken a validator, loosen a contract, or delete a test to make a check pass.
   If upstream changed, adapt in `scout/ingest.py` (usually `COLUMN_ALIASES`).
3. Every number printed in a report goes through `Ledger.num`, `Ledger.rank` or `Ledger.text`.
   A hard-coded number in report text fails `make check-report`.
4. New metric = SQL in `scout/metrics.py` + a definition in its docstring + a test + a report
   section. Follow `.factory/skills/new-metric/SKILL.md`.
5. Use only games before `as_of`. A report must never see its own game.
6. Keep PRs small: one request or one fix per PR, with the `make check` output in the description.

## Basketball glossary

- Possession: FGA - ORB + TOV + 0.44 x FTA (per team, per game).
- Offensive / defensive rating: points scored / allowed per 100 possessions.
- eFG%: (FGM + 0.5 x 3PM) / FGA. TOV%: turnovers per possession. ORB%: share of own misses rebounded.
- Clutch: final 5:00 of the 4th quarter or OT, score within 5.
- Transition: a shot within a few seconds after the team gains possession (rebound, steal).
- Season types: 2 = regular season, 3 = playoffs. Team ids are ESPN ids; Valkyries = 129689.

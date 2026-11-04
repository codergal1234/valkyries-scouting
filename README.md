# Valkyries scouting factory

An automated opponent scouting report for the Golden State Valkyries, maintained by
[Factory](https://factory.ai) Droids. Built as an FDE-style prospect demo on public data.

> Independent project. Not affiliated with or endorsed by the Golden State Valkyries or the WNBA.
> Data: ESPN via [SportsDataverse](https://github.com/sportsdataverse) (public).

## What it does

1. **Ingest** the 2026 WNBA season (play-by-play, box scores, schedule). Raw files are kept
   exactly as served; normalization happens on the way to `data/clean/`.
2. **Validate** with data contracts plus basketball invariants. The key one: play-by-play
   points must sum to the box score for every team in every game (706 of 706 pass).
3. **Compute** ratings, four factors, shot zones, clutch, top players and head-to-head in SQL.
4. **Report** to Markdown + PDF. Every number goes through a ledger, and
   `check_report` proves no number in the text was typed by hand or invented by a model.
5. **Maintain itself.** When the feed breaks or a staffer asks for a new stat, a Droid opens
   the fix as a PR, and nothing merges unless `make check` passes.

## Quickstart

```bash
make setup            # creates .venv/ and installs the pinned requirements.txt into it
make check            # ingest + 13 data checks + tests + report number check
make report OPP=ATL   # reports/ATL_2026-10-31.md and .pdf (Finals Game 7 prep)
make report OPP=DAL ASOF=2026-09-27   # replay: first-round prep, using only earlier games
```

Every target runs `.venv/bin/python`. To use another interpreter, pass `PY=`, for example
`make setup check PY=/path/to/python`.

## How Factory is wired in

| Piece | File |
|---|---|
| Project rules and commands for agents | `AGENTS.md` |
| Fixes upstream breakage without weakening checks | `.factory/droids/pipeline-medic.md` |
| Turns staff requests into metrics | `.factory/droids/scout-analyst.md` |
| Read-only PR review | `.factory/droids/reviewer.md` |
| Repeatable recipe for a new stat | `.factory/skills/new-metric/SKILL.md` |
| Hook: Droids can't write to `data/raw/` | `.factory/hooks.json` |
| CI: `make check` + Droid review on every PR, nightly validate | `.github/workflows/check.yml` |

See `DEMO.md` for the two live loops.

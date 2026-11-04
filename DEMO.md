# Live demo

Two loops show the factory maintaining itself. Each runs in a Factory (Droid) session on this repo.

## Loop 1: the upstream feed changes shape

Public feeds rename columns without warning. This simulates one overnight.

```bash
make setup
make break-feed        # renames two play-by-play columns, the way an upstream change would
make ingest validate   # FAIL contract:pbp, with a hint naming the likely rename
```

Then hand it to the `pipeline-medic` Droid:

> `make validate` is failing after last night's ingest. Diagnose and fix it per AGENTS.md,
> add a regression test, run `make check`, and open a pull request.

What to watch:
- It reads the failure, inspects the raw data read-only, and adapts `scout/ingest.py`.
- If it tries to edit `data/raw/` to make the error go away, the project hook blocks it.
- Nothing merges unless `make check` passes and a human approves.

Reset afterwards with `make restore-feed`.

## Loop 2: a coach asks for a new stat

`docs/requests/001-transition.md` is a staff request for transition offense and defense.
Hand it to the `scout-analyst` Droid:

> Implement docs/requests/001-transition.md following the new-metric skill. Run `make check`
> and summarize for a coach what the new section shows.

What to watch:
- The new metric gets a written definition, a test, and a report section.
- Every new number goes through the report ledger, so `make check-report` still proves
  nothing was typed in by hand.

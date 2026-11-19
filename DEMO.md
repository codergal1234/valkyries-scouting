# Live demo

Two loops show the factory maintaining itself. Each runs in a Factory (Droid) session on this repo.

## Loop 1: the upstream feed changes shape

Public feeds rename columns without warning. The ingestion aliases now handle the two
renames simulated by `make break-feed` automatically.

### Current behavior: automatic recovery

```bash
make setup
make ingest            # download the feed before simulating a change
make break-feed        # renames two play-by-play columns, the way an upstream change would
make ingest validate   # PASS: ingest restores the canonical names in data/clean/
```

`data/raw/` keeps the simulated camelCase fields (`scoringPlay` and `scoreValue`).
Ingest maps them to `scoring_play` and `score_value` in the clean tables; validators
and contracts remain unchanged. No manual raw-file edits are needed.

If the feed is already simulated, run `make restore-feed` before `make break-feed`.
Reset afterwards with `make restore-feed`, then `make ingest validate` to rebuild the
clean tables from the restored feed. These are sanctioned demo commands, not hand-edits.

### Historical failure demo: before the fix

To reproduce the original incident, use a separate checkout of pre-fix commit
`769ff24` (the parent of the alias fix). Keep your normal checkout and its data untouched.

```bash
git clone https://github.com/codergal1234/valkyries-scouting.git valkyries-scouting-pre-fix
cd valkyries-scouting-pre-fix
git switch -c demo/upstream-rename 769ff24
make setup
make ingest
make break-feed
make ingest validate   # expected exit 2: FAIL contract:pbp, with likely-rename hints
```

Then hand the disposable checkout to the `pipeline-medic` Droid:

> `make validate` is failing after last night's ingest. Diagnose and fix it per AGENTS.md,
> add a regression test, and run `make check`. This is a historical demo; do not open
> a duplicate pull request for the already-fixed columns.

What to watch:
- It reads the failure, inspects the raw data read-only, and adapts `scout/ingest.py`.
- If it tries to edit `data/raw/` to make the error go away, the project hook blocks it.
- Nothing merges unless `make check` passes and a human approves.

Reset this checkout afterwards with `make restore-feed` and `make ingest validate`.

## Loop 2: a coach asks for a new stat

`docs/requests/001-transition.md` is a staff request for transition offense and defense.
Hand it to the `scout-analyst` Droid:

> Implement docs/requests/001-transition.md following the new-metric skill. Run `make check`
> and summarize for a coach what the new section shows.

What to watch:
- The new metric gets a written definition, a test, and a report section.
- Every new number goes through the report ledger, so `make check-report` still proves
  nothing was typed in by hand.

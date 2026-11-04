# Day 2 runbook (Mahi)

Everything below runs on your laptop in the repo folder. About 2 to 3 hours plus recording.

## 0. Setup (15 min)

```bash
brew install --cask droid          # or: curl -fsSL https://app.factory.ai/cli | sh
export FACTORY_API_KEY=fk-...      # from app.factory.ai settings
make setup && make check           # should end with "make check: all green"
git init && git add -A && git commit -m "Scouting factory: pipeline, validators, report"
gh repo create valkyries-scouting --public --source=. --push
```

Then in GitHub: Settings > Secrets > Actions > add `FACTORY_API_KEY` (for the PR review job).

## 1. Baseline readiness (10 min)

```bash
droid
> /readiness-report
```

Screenshot the level and the top failing criteria. Optional: `/readiness-fix`, review the diff,
commit what's good, rerun `/readiness-report`. Before/after = a result for the writeup.

## 2. Loop 1: the feed breaks overnight (20 min)

```bash
git checkout -b fix/upstream-rename
make break-feed        # simulates ESPN renaming two columns
make ingest validate   # FAIL contract:pbp, with a hint naming the rename
```

Then hand it to the Droid, hands off:

```bash
droid exec --auto medium "Use the pipeline-medic droid. make validate is failing after last \
night's ingest. Diagnose and fix it per AGENTS.md, add a regression test, and run make check."
```

What to watch for (and screen-record):
- It reads the FAIL output, inspects raw data read-only, and adds the aliases in `scout/ingest.py`.
- If it tries to touch `data/raw/`, the hook blocks it. That's a great moment to capture.
- `make check` green. Then commit, push, open the PR, and let CI + the reviewer droid comment.
- Merge. Then `make restore-feed` so your local raw copy matches upstream again.

## 3. Loop 2: a staff request becomes a feature (30 to 45 min)

```bash
git checkout main && git pull && git checkout -b feat/transition
droid exec --auto medium "Use the scout-analyst droid to implement docs/requests/001-transition.md \
following the new-metric skill. Run make check and summarize for a coach."
make report OPP=ATL
```

Open `reports/ATL_2026-10-31.pdf` and sanity-check the new Transition section as a basketball
person. That judgment is your edge, so note anything off and have the Droid fix it.
PR, CI, reviewer droid, merge.

## 4. Record the 5-minute demo

1. (30s) The problem: opponent prep is manual; feeds break; staff asks wait on engineers.
2. (60s) The Game 7 report PDF. "How to guard them" + the number checker passing.
3. (90s) Loop 1 sped up: break, FAIL, Droid fix, green.
4. (90s) Loop 2 sped up: Slack-style request to merged section in the report.
5. (30s) Results: readiness before/after, 2 Droid PRs merged, 0 unverified numbers,
   and what you'd change about Factory.

## 5. Notes to keep while you work (for the writeup)

Write down every time Droid surprised you, got stuck, or needed a nudge, plus cost per run
from the session summary. That becomes the "product feedback for Factory" page, which is the
part an FDE hiring manager cares about most.

"""Number checker: a report may only contain numbers that were computed from data.

    python -m scout.check_report reports/ATL_2026-10-31.md

Two checks:
1. Recompute: rebuild the ledger from data/clean for the same opponent and date.
   Every saved value must match. Catches stale or hand-edited reports.
2. Scan: every number in the Markdown must appear in the ledger.
   Catches numbers typed into a template or written by a model.
"""
import json
import re
import sys
from pathlib import Path

from scout.report import compute

DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
NUM = re.compile(r"(?<![A-Za-z0-9.])[-+]?\d+(?:\.\d+)?(?:st|nd|rd|th)?(?![A-Za-z0-9])")


LIST_MARKER = re.compile(r"^\s*\d+\.\s", re.MULTILINE)


def tokens(text):
    text = LIST_MARKER.sub("", text)  # "1. " list numbering is formatting, not data
    dates = DATE.findall(text)
    rest = DATE.sub(" ", text)
    return dates + NUM.findall(rest)


def check(md_path: Path):
    ledger_path = md_path.with_suffix("").with_suffix(".ledger.json")
    if not ledger_path.exists():
        ledger_path = Path(str(md_path).removesuffix(".md") + ".ledger.json")
    saved = json.loads(ledger_path.read_text())
    errors = []

    fresh = compute(saved["opponent"], saved["game_date"])["ledger"]
    for key, val in saved["values"].items():
        if fresh.get(key) != val:
            errors.append(f"stale value {key}: report says {val!r}, data says {fresh.get(key)!r}")

    allowed = set()
    for v in saved["values"].values():
        allowed.update(tokens(v))
        allowed.update(t.lstrip("+") for t in tokens(v))
    for tok in tokens(md_path.read_text()):
        if tok not in allowed and tok.lstrip("+") not in allowed:
            errors.append(f"number {tok!r} in the report is not in the ledger (not computed from data)")
    return errors


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print("usage: python -m scout.check_report <report.md> [...]")
        return 2
    bad = 0
    for p in argv:
        errs = check(Path(p))
        print(f"{'PASS' if not errs else 'FAIL'}  {p}")
        for e in errs:
            print(f"      {e}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

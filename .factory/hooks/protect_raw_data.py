#!/usr/bin/env python3
"""PreToolUse hook: block any Droid write to data/raw/ (the untouched upstream copy).

Reads the tool call as JSON on stdin. Exit 2 blocks the call and sends the
message on stderr back to the Droid so it can change course.
"""

import json
import re
import sys

PROTECTED = "data/raw"
WRITE_CMD = re.compile(r"(\brm\b|\bmv\b|\bcp\b|>|\btee\b|sed\s+-i|truncate|to_parquet|\bCOPY\b|write_)", re.I)

try:
    call = json.load(sys.stdin)
except Exception:  # noqa: BLE001
    sys.exit(0)  # never break the session on a malformed payload

tool = call.get("tool_name", "")
args = call.get("tool_input", {}) or {}
blob = json.dumps(args)

if PROTECTED not in blob:
    sys.exit(0)

if tool in ("Execute", "Bash"):
    cmd = str(args.get("command", ""))
    if not WRITE_CMD.search(cmd):
        sys.exit(0)  # reads are fine (DESCRIBE, SELECT, ls)

print(
    f"Blocked: {tool} would modify {PROTECTED}/, which must stay exactly as upstream served it. "
    "Adapt to upstream changes in scout/ingest.py (COLUMN_ALIASES) instead.",
    file=sys.stderr,
)
sys.exit(2)

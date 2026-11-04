"""Demo helper: simulate the upstream feed changing shape overnight.

    python scripts/simulate_upstream_change.py           # break it
    python scripts/simulate_upstream_change.py --restore # put the original back

Renames two play-by-play columns to camelCase, the kind of silent change a
public feed makes without notice. A human runs this; Droids are blocked from
writing to data/raw by the project hook.
"""
import argparse
import shutil
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scout.config import RAW  # noqa: E402

RENAMES = {"score_value": "scoreValue", "scoring_play": "scoringPlay"}

ap = argparse.ArgumentParser()
ap.add_argument("--restore", action="store_true")
args = ap.parse_args()

src = RAW / "pbp.parquet"
backup = RAW / "pbp.original.parquet"

if args.restore:
    if backup.exists():
        shutil.move(backup, src)
        print("restored original pbp.parquet")
    else:
        print("nothing to restore")
    sys.exit(0)

if backup.exists():
    sys.exit("already simulated; run with --restore first")
shutil.copy(src, backup)
con = duckdb.connect()
cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{backup}'").fetchall()]
sel = ", ".join(f'"{c}" AS "{RENAMES.get(c, c)}"' for c in cols)
tmp = RAW / "pbp.tmp.parquet"
con.execute(f"COPY (SELECT {sel} FROM '{backup}') TO '{tmp}' (FORMAT parquet)")
tmp.replace(src)
print("upstream change simulated: " + ", ".join(f"{a} -> {b}" for a, b in RENAMES.items()))

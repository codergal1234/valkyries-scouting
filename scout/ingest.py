"""Ingest: download raw season files, then write normalized clean tables.

    python -m scout.ingest            # download missing files, rebuild clean/
    python -m scout.ingest --refresh  # re-download everything (nightly job)

Raw files are stored byte-for-byte as served and are never edited.
All normalization (renames, filters) happens on the way to data/clean/.
"""

import argparse
import hashlib
import json
import sys
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from scout.config import CLEAN, PLAYOFFS, RAW, REGULAR_SEASON, SOURCE_BASE, SOURCES
from scout.db import scalar

# Upstream column name -> name the pipeline expects.
# When the source renames a column, add the mapping here instead of touching raw data.
COLUMN_ALIASES: dict[str, dict[str, str]] = {
    "pbp": {},
    "team_box": {},
    "player_box": {},
    "schedule": {},
}


def raw_path(table: str) -> Path:
    return RAW / f"{table}.parquet"


def clean_path(table: str) -> Path:
    return CLEAN / f"{table}.parquet"


def download(table: str, refresh: bool = False, retries: int = 3) -> bool:
    dest = raw_path(table)
    if dest.exists() and not refresh:
        return False
    url = f"{SOURCE_BASE}/{SOURCES[table]}"
    tmp = dest.with_suffix(".part")
    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlretrieve(url, tmp)
            tmp.replace(dest)  # atomic swap: a failed download never leaves a half file
            return True
        except Exception as exc:  # noqa: BLE001
            if attempt == retries:
                raise RuntimeError(f"download failed for {table} from {url}: {exc}") from exc
            time.sleep(2**attempt)
    return False


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def select_with_aliases(con: duckdb.DuckDBPyConnection, table: str) -> str:
    cols = [r[0] for r in con.execute(f"DESCRIBE SELECT * FROM '{raw_path(table)}'").fetchall()]
    aliases = COLUMN_ALIASES.get(table, {})
    parts = [f'"{c}" AS "{aliases[c]}"' if c in aliases else f'"{c}"' for c in cols]
    return f"SELECT {', '.join(parts)} FROM '{raw_path(table)}'"


def build_clean() -> dict[str, int]:
    CLEAN.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    for table in SOURCES:
        con.execute(f"CREATE OR REPLACE VIEW raw_{table} AS {select_with_aliases(con, table)}")

    # Franchises = teams with a real regular-season schedule. Drops the All-Star game.
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE franchises AS
        SELECT team_id FROM raw_team_box WHERE season_type = {REGULAR_SEASON}
        GROUP BY team_id HAVING count(*) >= 10
    """)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE keep_games AS
        SELECT game_id FROM raw_team_box
        WHERE season_type IN ({REGULAR_SEASON}, {PLAYOFFS})
        GROUP BY game_id
        HAVING bool_and(team_id IN (SELECT team_id FROM franchises))
    """)
    for table in ("pbp", "team_box", "player_box"):
        con.execute(f"""
            COPY (SELECT * FROM raw_{table} WHERE game_id IN (SELECT game_id FROM keep_games))
            TO '{clean_path(table)}' (FORMAT parquet)
        """)
    con.execute(f"""
        COPY (SELECT * FROM raw_schedule WHERE season_type IN ({REGULAR_SEASON}, {PLAYOFFS})
              AND home_id IN (SELECT team_id FROM franchises))
        TO '{clean_path("schedule")}' (FORMAT parquet)
    """)
    counts = {t: int(scalar(con, f"SELECT count(*) FROM '{clean_path(t)}'")) for t in SOURCES}
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-download raw files")
    args = ap.parse_args(argv)
    RAW.mkdir(parents=True, exist_ok=True)
    fetched = [t for t in SOURCES if download(t, refresh=args.refresh)]
    counts = build_clean()
    manifest = {
        "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "downloaded": fetched,
        "raw_sha256": {t: sha256(raw_path(t)) for t in SOURCES},
        "clean_rows": counts,
    }
    (CLEAN / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest["clean_rows"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())

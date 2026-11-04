"""Cut a small, committed fixture from data/clean: two real games, all four tables.

    python scripts/make_fixtures.py

Tests run against these files, so they pass without downloading the season.
"""
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scout.config import CLEAN, FIXTURES  # noqa: E402

GAMES = (401918310, 401918309)  # 2026 Finals Games 6 and 5, GS vs ATL

out = FIXTURES / "good"
out.mkdir(parents=True, exist_ok=True)
con = duckdb.connect()
ids = ", ".join(map(str, GAMES))
for t in ("pbp", "team_box", "player_box", "schedule"):
    con.execute(f"COPY (SELECT * FROM '{CLEAN / f'{t}.parquet'}' WHERE game_id IN ({ids})) "
                f"TO '{out / f'{t}.parquet'}' (FORMAT parquet)")
    print(t, con.execute(f"SELECT count(*) FROM '{out / f'{t}.parquet'}'").fetchone()[0])

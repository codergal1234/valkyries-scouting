"""Shared paths and constants. One place to change the season or the client team."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "raw"  # exactly what the upstream source served. Never edited.
CLEAN = DATA / "clean"  # normalized tables the rest of the pipeline reads.
REPORTS = ROOT / "reports"
FIXTURES = ROOT / "tests" / "fixtures"

SEASON = 2026
CLIENT_TEAM_ID = 129689  # Golden State Valkyries (ESPN team id)
CLIENT_ABBR = "GS"

# Public SportsDataverse mirrors of ESPN WNBA data (same source wehoop uses).
SOURCE_BASE = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
SOURCES = {
    "pbp": f"espn_wnba_pbp/play_by_play_{SEASON}.parquet",
    "team_box": f"espn_wnba_team_boxscores/team_box_{SEASON}.parquet",
    "player_box": f"espn_wnba_player_boxscores/player_box_{SEASON}.parquet",
    "schedule": f"espn_wnba_schedules/wnba_schedule_{SEASON}.parquet",
}

REGULAR_SEASON, PLAYOFFS = 2, 3

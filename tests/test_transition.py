"""Transition tests use real fixture schemas, never rewrite committed fixture/raw bytes."""

from collections.abc import Sequence
from typing import Any

import duckdb
import pandas as pd
import pytest

from scout.config import FIXTURES
from scout.metrics import transition
from scout.report import Ledger, guard_keys, to_markdown, transition_blocks

GS = 129689
ATL = 20
GOOD = FIXTURES / "good"
# seconds, team, event, points, points attempted
Event = tuple[float, int, str, int, int]


def fixture_connection() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for table in ("pbp", "team_box"):
        con.execute(f"CREATE VIEW {table} AS SELECT * FROM '{GOOD / f'{table}.parquet'}'")
    return con


def synthetic(events: Sequence[Event]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("""
        CREATE TABLE cases (num INTEGER, secs DOUBLE, team INTEGER, kind VARCHAR, pts INTEGER, pa INTEGER)
    """)
    con.executemany("INSERT INTO cases VALUES (?, ?, ?, ?, ?, ?)", [(i, *e) for i, e in enumerate(events, 1)])
    con.execute(f"""
        CREATE TABLE pbp AS
        SELECT b.* REPLACE (
            1 AS game_id, c.num AS game_play_number, c.num AS sequence_number,
            1 AS period_number, c.secs AS start_quarter_seconds_remaining,
            c.team AS team_id, {GS} AS home_team_id, {ATL} AS away_team_id,
            c.kind AS type_text, c.kind AS text, c.pts AS score_value,
            c.pa AS points_attempted, (c.pa > 0) AS shooting_play, (c.pts > 0) AS scoring_play,
            DATE '2026-10-26' AS game_date, 3 AS season_type
        )
        FROM (SELECT * FROM '{GOOD / "pbp.parquet"}' LIMIT 1) b CROSS JOIN cases c
    """)
    con.execute(f"""
        CREATE TABLE team_box AS
        SELECT * REPLACE (1 AS game_id, 100 AS team_score, 100 AS opponent_team_score)
        FROM '{GOOD / "team_box.parquet"}' WHERE game_id = 401918309
    """)
    return con


def test_hand_checked_fixture() -> None:
    with fixture_connection() as con:
        atl = transition(con, ATL, "2026-10-29")
        gs = transition(con, GS, "2026-10-29")
        # Game 5 ATL qualifying plays: 18,22,65,78,130,141,267,280,324,337,356.
        # Only 22 (2 points) and 356 (3 points) score; 23's and-one misses.
        assert atl["offense_points"] == 5
        assert atl["offense_possessions"] == 11
        assert atl["offense_share"] == pytest.approx(100 * 5 / 55)
        assert atl["offense_ppp"] == pytest.approx(5 / 11)
        # GS: 16,27,44,76,111,236,244,287; 44=2,111=3,236=2.
        assert gs["offense_points"] == 7
        assert gs["offense_possessions"] == 8
        assert gs["offense_share"] == pytest.approx(100 * 7 / 64)
        assert gs["offense_ppp"] == pytest.approx(7 / 8)
        assert atl["defense_points"] == gs["offense_points"]
        assert atl["defense_possessions"] == gs["offense_possessions"]
        assert atl["defense_share"] == gs["offense_share"]
        assert atl["defense_ppp"] == gs["offense_ppp"]
        assert (atl["offense_rank"], gs["offense_rank"]) == (2, 1)
        assert (atl["defense_rank"], gs["defense_rank"]) == (2, 1)
        both = transition(con, GS, "2026-10-30")
        # Game 6 GS: 28,144,151,164,211,214,227,245,332,364,371,383.
        # 164=2,214=2,227=3,332=1 FT (335, after administrative rebound),371=3 and-one.
        # ATL: 50,102,105,121,146,149,187,209; 50=2,102=3,121=2,146=2.
        assert (both["offense_points"], both["offense_possessions"]) == (18, 20)
        assert (both["defense_points"], both["defense_possessions"]) == (14, 19)
        assert both["offense_share"] == pytest.approx(100 * 18 / 133)
        assert both["defense_share"] == pytest.approx(100 * 14 / 135)


@pytest.mark.parametrize("elapsed,expected", [(0, 1), (8, 1), (8.01, 0), (9, 0), (-1, 0)])
def test_clock_boundary(elapsed: float, expected: int) -> None:
    with synthetic([(100, GS, "Defensive Rebound", 0, 0), (100 - elapsed, GS, "Jump Shot", 2, 2)]) as con:
        result = transition(con, GS, "2026-10-29")
        assert result["offense_points"] == 2 * expected
        assert result["offense_possessions"] == expected
        assert result["offense_ppp"] == (2 if expected else None)


def test_misses_multiple_attempts_and_no_clock_restart() -> None:
    with synthetic(
        [
            (100, GS, "Defensive Rebound", 0, 0),
            (96, GS, "Jump Shot", 0, 2),
            (95, GS, "Offensive Rebound", 0, 0),
            (94, GS, "Jump Shot", 0, 2),
            (93, GS, "Offensive Rebound", 0, 0),
            (91, GS, "Jump Shot", 3, 3),  # late half-court basket, not transition points
            (80, GS, "Defensive Rebound", 0, 0),
            (78, GS, "Jump Shot", 2, 2),
            (77, GS, "Jump Shot", 2, 2),  # stale anchor after a made basket
        ]
    ) as con:
        result = transition(con, GS, "2026-10-29")
        assert (result["offense_points"], result["offense_possessions"], result["offense_ppp"]) == (2, 2, 1)


@pytest.mark.parametrize("kind", ["Bad Pass\nTurnover", "Traveling", "Out of Bounds - Bad Pass Turnover"])
def test_opponent_turnover_and_owner_changes(kind: str) -> None:
    with synthetic(
        [
            (100, ATL, kind, 0, 0),
            (98, GS, "Jump Shot", 0, 2),
            (97, GS, "Lost Ball Turnover", 0, 0),
            (95, ATL, "Jump Shot", 3, 3),
            (94, GS, "Jump Shot", 2, 2),  # cannot use old acquisition after own turnover
        ]
    ) as con:
        gs = transition(con, GS, "2026-10-29")
        assert (gs["offense_points"], gs["offense_possessions"]) == (0, 1)
        assert (gs["defense_points"], gs["defense_possessions"], gs["defense_ppp"]) == (3, 1, 3)


@pytest.mark.parametrize(
    "kind",
    ["Personal Foul", "Full Timeout", "Substitution", "Jumpball", "Ref-Initiated Review (Supported)", "Kicked Ball"],
)
def test_stoppages_end_transition(kind: str) -> None:
    with synthetic([(100, GS, "Defensive Rebound", 0, 0), (99, ATL, kind, 0, 0), (98, GS, "Jump Shot", 2, 2)]) as con:
        assert transition(con, GS, "2026-10-29")["offense_possessions"] == 0


def test_team_rebound_is_not_live_acquisition() -> None:
    with synthetic([(100, GS, "Defensive Rebound", 0, 0), (98, GS, "Jump Shot", 2, 2)]) as con:
        con.execute("UPDATE pbp SET text = 'Valkyries defensive team rebound' WHERE game_play_number = 1")
        assert transition(con, GS, "2026-10-29")["offense_possessions"] == 0


@pytest.mark.parametrize("elapsed,points", [(8, 2), (8.01, 0)])
def test_shooting_foul_free_throws(elapsed: float, points: int) -> None:
    with synthetic(
        [
            (100, GS, "Defensive Rebound", 0, 0),
            (100 - elapsed, ATL, "Shooting Foul", 0, 0),
            (100 - elapsed, GS, "Free Throw - 1 of 2", 1, 1),
            (100 - elapsed, GS, "Substitution", 0, 0),
            (100 - elapsed, ATL, "Full Timeout", 0, 0),
            (100 - elapsed, GS, "Free Throw - Technical", 1, 1),
            (100 - elapsed, GS, "Free Throw - 2 of 2", 1, 1),
        ]
    ) as con:
        result = transition(con, GS, "2026-10-29")
        assert result["offense_points"] == points
        assert result["offense_possessions"] == bool(points)


def test_and_one_counted_once_and_bonus_excluded() -> None:
    with synthetic(
        [
            (100, GS, "Defensive Rebound", 0, 0),
            (92, GS, "Layup Shot", 2, 2),
            (92, ATL, "Shooting Foul", 0, 0),
            (92, GS, "Substitution", 0, 0),
            (92, GS, "Free Throw - 1 of 1", 1, 1),
            (80, ATL, "Bad Pass Turnover", 0, 0),
            (79, ATL, "Personal Foul", 0, 0),
            (79, GS, "Free Throw - 1 of 2", 1, 1),
            (79, GS, "Free Throw - 2 of 2", 1, 1),
        ]
    ) as con:
        result = transition(con, GS, "2026-10-29")
        assert (result["offense_points"], result["offense_possessions"], result["offense_ppp"]) == (3, 1, 3)


@pytest.mark.parametrize("intervening", ["Personal Foul", "Jump Shot", "Defensive Rebound"])
def test_free_throws_require_current_foul_link(intervening: str) -> None:
    with synthetic(
        [
            (100, GS, "Defensive Rebound", 0, 0),
            (98, ATL, "Shooting Foul", 0, 0),
            (98, ATL, intervening, 0, 0),
            (98, GS, "Free Throw - 1 of 2", 1, 1),
            (98, GS, "Free Throw - 2 of 2", 1, 1),
        ]
    ) as con:
        assert transition(con, GS, "2026-10-29")["offense_points"] == 0


def test_ft_clock_and_team_must_match_foul() -> None:
    with synthetic(
        [
            (100, GS, "Defensive Rebound", 0, 0),
            (98, ATL, "Shooting Foul", 0, 0),
            (98, ATL, "Free Throw - 1 of 2", 1, 1),  # wrong shooting team
            (97, GS, "Free Throw - 2 of 2", 1, 1),  # different clock
        ]
    ) as con:
        assert transition(con, GS, "2026-10-29")["offense_points"] == 0


@pytest.mark.parametrize(
    "kind", ["Free Throw - Technical", "Free Throw - Flagrant 1 of 2", "Free Throw - Clear Path 1 of 2"]
)
def test_nonordinary_free_throws_excluded(kind: str) -> None:
    with synthetic(
        [(100, GS, "Defensive Rebound", 0, 0), (98, ATL, "Shooting Foul", 0, 0), (98, GS, kind, 1, 1)]
    ) as con:
        assert transition(con, GS, "2026-10-29")["offense_points"] == 0


@pytest.mark.parametrize("column,value", [("period_number", 2), ("game_id", 2)])
def test_acquisition_does_not_cross_period_or_game(column: str, value: int) -> None:
    with synthetic([(5, GS, "Defensive Rebound", 0, 0), (1, GS, "Jump Shot", 2, 2)]) as con:
        con.execute(f"UPDATE pbp SET {column} = {value} WHERE game_play_number = 2")
        if column == "game_id":
            con.execute("INSERT INTO team_box SELECT * REPLACE (2 AS game_id) FROM team_box")
        assert transition(con, GS, "2026-10-29")["offense_possessions"] == 0


def test_overtime_uses_period_clock() -> None:
    with synthetic([(300, GS, "Defensive Rebound", 0, 0), (292, GS, "Jump Shot", 2, 2)]) as con:
        con.execute("UPDATE pbp SET period_number = 5")
        assert transition(con, GS, "2026-10-29")["offense_points"] == 2


def test_filters_and_zero_samples() -> None:
    with fixture_connection() as con:
        none = transition(con, GS, "2026-10-26")
        assert none["offense_share"] is None
        assert none["offense_rank"] is None
        assert none["offense_ppp"] is None
        assert none["defense_ppp"] is None
        assert none["offense_points"] == none["offense_possessions"] == 0
        assert transition(con, GS, "2026-10-30", (2,)) == none
        assert transition(con, GS, "2026-10-30", ()) == none
        assert transition(con, GS, "2026-10-30", (3,)) == transition(con, GS, "2026-10-30")
        assert transition(con, 999, "2026-10-30") == none
    with synthetic([(100, GS, "Defensive Rebound", 0, 0)]) as con:
        zero = transition(con, GS, "2026-10-29")
        assert zero["offense_share"] == zero["defense_share"] == 0
        assert zero["offense_ppp"] is None
        assert zero["offense_rank"] == zero["defense_rank"] == 1  # ties


def test_season_type_filters_both_points_and_rank() -> None:
    with synthetic([(100, GS, "Defensive Rebound", 0, 0), (98, GS, "Jump Shot", 2, 2)]) as con:
        con.execute("INSERT INTO pbp SELECT * REPLACE (2 AS game_id, 2 AS season_type, 20 AS score_value) FROM pbp")
        con.execute("INSERT INTO team_box SELECT * REPLACE (2 AS game_id, 2 AS season_type) FROM team_box")
        assert transition(con, GS, "2026-10-29", (3,))["offense_points"] == 2
        assert transition(con, GS, "2026-10-29", (2,))["offense_points"] == 20
        assert transition(con, GS, "2026-10-29")["offense_share"] == 11


@pytest.mark.parametrize("rank,required", [(1, True), (4, True), (5, False), (None, False)])
def test_guard_transition_slot_and_legacy_api(rank: int | None, required: bool) -> None:
    # Several existing candidates score four; a fourth-ranked transition adjustment must survive.
    opp: pd.Series[Any] = pd.Series(
        {
            "orb_rank": 1,
            "orb_pct": 30,
            "ft_rate_rank": 1,
            "ft_rate": 25,
            "tov_rank": 13,
            "tov_pct": 20,
            "opp_tov_rank": 1,
            "opp_tov_pct": 20,
        }
    )
    shares = {"rim": {"share_rank": 1, "share": 40}, "3pt": {"share_rank": 1, "share": 40}}
    stats = {"offense_rank": rank, "offense_share": 20}
    keys = guard_keys(Ledger(), opp, None, shares, [], {"games": 0}, 13, stats)
    assert len(keys) == 3
    assert any("Get back early" in k for k in keys) == required
    legacy = guard_keys(Ledger(), opp, None, shares, [], {"games": 0}, 13)
    assert not any("Get back early" in k for k in legacy)


def test_transition_report_values_and_no_sample() -> None:
    with fixture_connection() as con:
        lg = Ledger()
        stats = transition(con, GS, "2026-10-29")
        md = to_markdown(transition_blocks(lg, "ATL", stats, stats))
        assert "## Transition" in md
        assert lg.values["transition.opp.offense.share"] == "10.9"
        assert lg.values["transition.gs.defense.ppp"] == "0.45"
        assert lg.values["transition.gs.offense.possessions"] == "8"
        none = transition(con, GS, "2026-10-26")
        assert "N/A" in to_markdown(transition_blocks(lg, "ATL", none, none))

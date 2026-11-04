"""Metrics: every number in a scouting report is computed here, in SQL, from data/clean.

All functions take `as_of` (ISO date). Only games played BEFORE that date are used,
so a report for a past game never peeks at its own result.

Definitions
- Possessions (per team-game): FGA - ORB + TOV + 0.44 * FTA
- Offensive rating (ORtg): 100 * points / possessions
- Defensive rating (DRtg): 100 * opponent points / opponent possessions
- Net rating: ORtg - DRtg
- Pace: average of (team poss + opponent poss) / 2 per game
- eFG%: (FGM + 0.5 * 3PM) / FGA
- TOV%: turnovers / possessions
- ORB%: ORB / (ORB + opponent DRB)
- FT rate: FTA / FGA
- 3PA rate: 3PA / FGA
- Shot zones (play-by-play): 3 = any 3-point attempt; rim = layups, dunks, tips,
  putbacks, alley-oops; mid = every other 2-point attempt
- Clutch: 4th quarter or overtime, final 5:00 of the period, score within 5 before the play
"""

from collections.abc import Sequence

import duckdb
from pandas import DataFrame

from scout.config import CLEAN
from scout.db import Row, records

RIM_PATTERN = "(?i)(layup|dunk|tip shot|putback|alley oop|finger roll)"


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for t in ("pbp", "team_box", "player_box", "schedule"):
        con.execute(f"CREATE VIEW {t} AS SELECT * FROM '{CLEAN / f'{t}.parquet'}'")
    con.execute("""
        CREATE MACRO poss(fga, orb, tov, fta) AS fga - orb + tov + 0.44 * fta
    """)
    return con


def _games(as_of: str, season_types: Sequence[int] = (2, 3)) -> str:
    st = ", ".join(str(s) for s in season_types)
    return f"game_date < DATE '{as_of}' AND season_type IN ({st})"


def team_table(con: duckdb.DuckDBPyConnection, as_of: str, season_types: Sequence[int] = (2, 3)) -> DataFrame:
    """One row per team with season ratings, four factors and league ranks (1 = best)."""
    sql = f"""
    WITH g AS (
        SELECT a.team_id, a.team_abbreviation abbr, a.team_display_name name, a.team_winner win,
               a.team_score pts, b.team_score opp_pts,
               poss(a.field_goals_attempted, a.offensive_rebounds, a.total_turnovers, a.free_throws_attempted) p,
               poss(b.field_goals_attempted, b.offensive_rebounds, b.total_turnovers, b.free_throws_attempted) op,
               a.field_goals_made fgm, a.field_goals_attempted fga, a.three_point_field_goals_made tpm,
               a.three_point_field_goals_attempted tpa, a.free_throws_attempted fta, a.total_turnovers tov,
               a.offensive_rebounds orb, b.defensive_rebounds opp_drb,
               b.field_goals_made o_fgm, b.field_goals_attempted o_fga, b.three_point_field_goals_made o_tpm,
               b.total_turnovers o_tov, b.three_point_field_goals_attempted o_tpa
        FROM team_box a JOIN team_box b ON a.game_id = b.game_id AND b.team_id = a.opponent_team_id
        WHERE a.game_date < DATE '{as_of}' AND a.season_type IN ({", ".join(map(str, season_types))})
    ), s AS (
        SELECT team_id, any_value(abbr) abbr, any_value(name) name, count(*) games,
               sum(win::INT) wins, count(*) - sum(win::INT) losses,
               100 * sum(pts) / sum(p) ortg, 100 * sum(opp_pts) / sum(op) drtg,
               avg((p + op) / 2) pace,
               100 * (sum(fgm) + 0.5 * sum(tpm)) / sum(fga) efg,
               100 * sum(tov) / sum(p) tov_pct,
               100 * sum(orb) / (sum(orb) + sum(opp_drb)) orb_pct,
               100 * sum(fta) / sum(fga) ft_rate,
               100 * sum(tpa) / sum(fga) three_rate,
               100 * (sum(o_fgm) + 0.5 * sum(o_tpm)) / sum(o_fga) opp_efg,
               100 * sum(o_tov) / sum(op) opp_tov_pct,
               100 * sum(o_tpa) / sum(o_fga) opp_three_rate,
               sum(pts) / count(*) ppg
        FROM g GROUP BY team_id
    )
    SELECT *, ortg - drtg net,
        rank() OVER (ORDER BY ortg DESC) ortg_rank,
        rank() OVER (ORDER BY drtg ASC) drtg_rank,
        rank() OVER (ORDER BY ortg - drtg DESC) net_rank,
        rank() OVER (ORDER BY pace DESC) pace_rank,
        rank() OVER (ORDER BY efg DESC) efg_rank,
        rank() OVER (ORDER BY tov_pct ASC) tov_rank,
        rank() OVER (ORDER BY orb_pct DESC) orb_rank,
        rank() OVER (ORDER BY ft_rate DESC) ft_rate_rank,
        rank() OVER (ORDER BY three_rate DESC) three_rate_rank,
        rank() OVER (ORDER BY opp_efg ASC) opp_efg_rank,
        rank() OVER (ORDER BY opp_tov_pct DESC) opp_tov_rank,
        count(*) OVER () teams
    FROM s ORDER BY net DESC
    """
    return con.execute(sql).df()


def shot_profile(
    con: duckdb.DuckDBPyConnection,
    team_id: int,
    as_of: str,
    side: str = "offense",
    season_types: Sequence[int] = (2, 3),
) -> dict[str, Row]:
    """Share of field-goal attempts and FG% by zone. side='defense' = what opponents shoot against them."""
    team_filter = (
        f"team_id = {team_id}"
        if side == "offense"
        else f"team_id <> {team_id} AND {team_id} IN (home_team_id, away_team_id)"
    )
    sql = f"""
    WITH s AS (
        SELECT CASE WHEN points_attempted = 3 THEN '3pt'
                    WHEN regexp_matches(type_text, '{RIM_PATTERN}') THEN 'rim'
                    ELSE 'mid' END zone,
               scoring_play made
        FROM pbp
        WHERE shooting_play AND points_attempted IN (2, 3) AND {team_filter}
          AND {_games(as_of, season_types)}
    )
    SELECT zone, count(*) fga, 100 * count(*) / sum(count(*)) OVER () share,
           100 * avg(made::INT) fg_pct
    FROM s GROUP BY zone ORDER BY zone
    """
    return {r["zone"]: r for r in records(con.execute(sql).df())}


def league_shot_shares(con: duckdb.DuckDBPyConnection, as_of: str, season_types: Sequence[int] = (2, 3)) -> DataFrame:
    """Each team's offensive zone shares, with league rank by share (1 = takes the most)."""
    sql = f"""
    WITH s AS (
        SELECT team_id, CASE WHEN points_attempted = 3 THEN '3pt'
                    WHEN regexp_matches(type_text, '{RIM_PATTERN}') THEN 'rim' ELSE 'mid' END zone
        FROM pbp WHERE shooting_play AND points_attempted IN (2, 3) AND team_id IS NOT NULL
          AND {_games(as_of, season_types)}
    ), c AS (
        SELECT team_id, zone, 100 * count(*) / sum(count(*)) OVER (PARTITION BY team_id) share
        FROM s GROUP BY team_id, zone
    )
    SELECT *, rank() OVER (PARTITION BY zone ORDER BY share DESC) share_rank FROM c
    """
    return con.execute(sql).df()


def clutch(con: duckdb.DuckDBPyConnection, team_id: int, as_of: str, season_types: Sequence[int] = (2, 3)) -> Row:
    """Points scored and allowed in clutch time, plus clutch games played."""
    sql = f"""
    WITH p AS (
        SELECT game_id, team_id, scoring_play, score_value,
               home_team_id, away_team_id,
               lag(home_score, 1, 0) OVER w prev_home, lag(away_score, 1, 0) OVER w prev_away,
               period_number, start_quarter_seconds_remaining secs
        FROM pbp WHERE {team_id} IN (home_team_id, away_team_id) AND {_games(as_of, season_types)}
        WINDOW w AS (PARTITION BY game_id ORDER BY game_play_number)
    ), c AS (
        SELECT * FROM p WHERE period_number >= 4 AND secs <= 300 AND abs(prev_home - prev_away) <= 5
    )
    SELECT count(DISTINCT game_id) games,
           coalesce(sum(CASE WHEN scoring_play AND team_id = {team_id} THEN score_value END), 0) pts_for,
           coalesce(sum(CASE WHEN scoring_play AND team_id <> {team_id} THEN score_value END), 0) pts_against
    FROM c
    """
    r = records(con.execute(sql).df())[0]
    r["net"] = r["pts_for"] - r["pts_against"]
    return r


def top_players(
    con: duckdb.DuckDBPyConnection,
    team_id: int,
    as_of: str,
    n: int = 5,
    min_games: int = 8,
    season_types: Sequence[int] = (2, 3),
) -> list[Row]:
    sql = f"""
    SELECT athlete_display_name name, count(*) games, avg(minutes) mpg, avg(points) ppg,
           avg(rebounds) rpg, avg(assists) apg,
           100 * sum(points) / nullif(2 * (sum(field_goals_attempted) + 0.44 * sum(free_throws_attempted)), 0) ts_pct,
           100 * sum(three_point_field_goals_made) / nullif(sum(three_point_field_goals_attempted), 0) three_pct,
           avg(three_point_field_goals_attempted) tpa_pg,
           100 * sum(points) / (SELECT sum(team_score) FROM team_box WHERE team_id = {team_id}
                                AND {_games(as_of, season_types)}) pts_share
    FROM player_box
    WHERE team_id = {team_id} AND NOT coalesce(did_not_play, false) AND minutes > 0
      AND {_games(as_of, season_types)}
    GROUP BY athlete_id, athlete_display_name HAVING count(*) >= {min_games}
    ORDER BY ppg DESC LIMIT {n}
    """
    return records(con.execute(sql).df())


def recent_form(
    con: duckdb.DuckDBPyConnection, team_id: int, as_of: str, n: int = 10, season_types: Sequence[int] = (2, 3)
) -> Row:
    sql = f"""
    WITH g AS (
        SELECT a.game_date, a.team_winner win, a.team_score pts, b.team_score opp_pts,
               poss(a.field_goals_attempted, a.offensive_rebounds, a.total_turnovers, a.free_throws_attempted) p,
               poss(b.field_goals_attempted, b.offensive_rebounds, b.total_turnovers, b.free_throws_attempted) op
        FROM team_box a JOIN team_box b ON a.game_id = b.game_id AND b.team_id = a.opponent_team_id
        WHERE a.team_id = {team_id} AND a.game_date < DATE '{as_of}'
          AND a.season_type IN ({", ".join(map(str, season_types))})
        ORDER BY a.game_date DESC LIMIT {n}
    )
    SELECT count(*) games, sum(win::INT) wins, count(*) - sum(win::INT) losses,
           100 * sum(pts) / sum(p) - 100 * sum(opp_pts) / sum(op) net
    FROM g
    """
    return records(con.execute(sql).df())[0]


def head_to_head(
    con: duckdb.DuckDBPyConnection, team_id: int, opp_id: int, as_of: str, season_types: Sequence[int] = (2, 3)
) -> list[Row]:
    sql = f"""
    SELECT game_date, season_type, team_score pts, opponent_team_score opp_pts, team_winner win
    FROM team_box WHERE team_id = {team_id} AND opponent_team_id = {opp_id}
      AND {_games(as_of, season_types)}
    ORDER BY game_date
    """
    return records(con.execute(sql).df())


def team_id_for(con: duckdb.DuckDBPyConnection, abbr: str) -> tuple[int, str]:
    row = con.execute(
        "SELECT DISTINCT team_id, team_display_name FROM team_box WHERE upper(team_abbreviation) = upper(?)", [abbr]
    ).fetchone()
    if not row:
        valid = [r[0] for r in con.execute("SELECT DISTINCT team_abbreviation FROM team_box ORDER BY 1").fetchall()]
        raise SystemExit(f"Unknown team '{abbr}'. Valid: {', '.join(valid)}")
    return row[0], row[1]

"""Validators: deterministic checks that must all pass before anything ships.

    python -m scout.validate                 # check data/clean
    python -m scout.validate --dir <path>    # check another folder (tests use fixtures)

Exit code 0 = all checks pass, 1 = at least one failed. Every failure names
the check, the table and an example of the bad rows so a human or a Droid
can go straight to the cause.
"""

import argparse
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from scout.config import CLEAN
from scout.contracts import CONTRACTS


@dataclass
class Result:
    name: str
    ok: bool
    detail: str = ""


def _con(folder: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    for table in CONTRACTS:
        path = folder / f"{table}.parquet"
        if path.exists():
            con.execute(f"CREATE VIEW {table} AS SELECT * FROM '{path}'")
    return con


def _norm(name: str) -> str:
    return name.replace("_", "").lower()


def check_contracts(con: duckdb.DuckDBPyConnection, folder: Path) -> list[Result]:
    out: list[Result] = []
    for table, cols in CONTRACTS.items():
        if not (folder / f"{table}.parquet").exists():
            out.append(Result(f"contract:{table}", False, f"missing file {table}.parquet"))
            continue
        actual = {r[0]: r[1] for r in con.execute(f"DESCRIBE {table}").fetchall()}
        missing = [c for c in cols if c not in actual]
        wrong = [f"{c} is {actual[c]}, expected {t}" for c, t in cols.items() if c in actual and actual[c] != t]
        problems = [f"missing column '{c}'" for c in missing] + wrong
        if problems:
            extra = set(actual) - set(cols)
            guesses = [f"'{c}' may have been renamed to '{e}'" for c in missing for e in extra if _norm(e) == _norm(c)]
            hint = f" (likely upstream rename: {'; '.join(guesses)})" if guesses else ""
            out.append(Result(f"contract:{table}", False, "; ".join(problems) + hint))
        else:
            out.append(Result(f"contract:{table}", True))
    return out


def _query_check(con: duckdb.DuckDBPyConnection, name: str, sql: str, describe: str) -> Result:
    """sql returns the BAD rows. Zero rows = pass."""
    rows = con.execute(sql).fetchall()
    if not rows:
        return Result(name, True)
    return Result(name, False, f"{len(rows)} bad rows; {describe}; first: {rows[0]}")


def check_invariants(con: duckdb.DuckDBPyConnection) -> list[Result]:
    checks = [
        (
            "nonempty:all_tables",
            "SELECT 'empty' FROM (SELECT (SELECT count(*) FROM pbp) a, (SELECT count(*) FROM team_box) b,"
            " (SELECT count(*) FROM player_box) c) WHERE a = 0 OR b = 0 OR c = 0",
            "a clean table has zero rows",
        ),
        (
            "team_box:unique_team_game",
            "SELECT game_id, team_id, count(*) n FROM team_box GROUP BY 1, 2 HAVING n > 1",
            "(game_id, team_id) repeats",
        ),
        (
            "team_box:two_teams_per_game",
            "SELECT game_id, count(*) n FROM team_box GROUP BY 1 HAVING n <> 2",
            "a game does not have exactly 2 team rows",
        ),
        (
            "team_box:opponent_scores_agree",
            "SELECT a.game_id, a.team_id FROM team_box a JOIN team_box b"
            " ON a.game_id = b.game_id AND a.team_id = b.opponent_team_id"
            " WHERE a.opponent_team_score <> b.team_score",
            "a team's opponent_team_score differs from the opponent's own team_score",
        ),
        (
            "team_box:points_add_up",
            "SELECT game_id, team_id, team_score FROM team_box WHERE team_score <>"
            " 2 * field_goals_made + three_point_field_goals_made + free_throws_made",
            "team_score != 2*FGM + 3PM + FTM",
        ),
        (
            "pbp:points_match_box",
            "WITH p AS (SELECT game_id, team_id, sum(CASE WHEN scoring_play THEN score_value ELSE 0 END) pts"
            " FROM pbp WHERE team_id IS NOT NULL GROUP BY 1, 2)"
            " SELECT t.game_id, t.team_id, t.team_score, coalesce(p.pts, 0) pbp_pts FROM team_box t"
            " LEFT JOIN p USING (game_id, team_id) WHERE coalesce(p.pts, 0) <> t.team_score",
            "play-by-play points do not sum to the box score",
        ),
        (
            "player_box:points_match_team",
            "WITH p AS (SELECT game_id, team_id, sum(coalesce(points, 0)) pts FROM player_box GROUP BY 1, 2)"
            " SELECT t.game_id, t.team_id, t.team_score, p.pts FROM team_box t JOIN p USING (game_id, team_id)"
            " WHERE p.pts <> t.team_score",
            "player points do not sum to the team score",
        ),
        (
            "schedule:completed_games_have_box",
            "SELECT s.game_id, s.game_date FROM schedule s WHERE s.status_type_completed"
            " AND s.game_id NOT IN (SELECT game_id FROM team_box)",
            "a completed game has no box score (stale or partial feed)",
        ),
        (
            "team_box:no_future_games",
            f"SELECT game_id, game_date FROM team_box WHERE game_date > DATE '{date.today().isoformat()}'",
            "box score dated in the future",
        ),
    ]
    out: list[Result] = []
    for name, sql, describe in checks:
        try:
            out.append(_query_check(con, name, sql, describe))
        except duckdb.Error as exc:
            out.append(Result(name, False, f"could not run: {str(exc).splitlines()[0]}"))
    return out


def run(folder: Path = CLEAN) -> list[Result]:
    con = _con(folder)
    results = check_contracts(con, folder)
    if all(r.ok for r in results):
        results += check_invariants(con)
    else:
        results.append(Result("invariants", False, "skipped because a data contract failed; fix contracts first"))
    return results


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=CLEAN)
    args = ap.parse_args(argv)
    results = run(args.dir)
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name}" + (f"\n      {r.detail}" if r.detail else ""))
    failed = [r for r in results if not r.ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

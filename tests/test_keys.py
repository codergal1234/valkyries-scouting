"""Scouting keys must describe the correct side of the ball."""

from typing import Any

import pandas as pd
import pytest

from scout import metrics, report
from scout.config import FIXTURES
from scout.report import Ledger, guard_keys, offensive_keys


def opponent(**overrides: float) -> "pd.Series[Any]":
    values = {
        "orb_rank": 5,
        "orb_pct": 30,
        "ft_rate_rank": 5,
        "ft_rate": 25,
        "tov_rank": 1,
        "tov_pct": 20,
        "opp_tov_rank": 5,
        "opp_tov_pct": 18,
    }
    return pd.Series(values | overrides)


@pytest.mark.parametrize("rank,expected", [(1, True), (4, True), (5, False)])
def test_value_ball_only_in_offensive_keys(rank: int, expected: bool) -> None:
    opp = opponent(opp_tov_rank=rank)
    lg = Ledger()
    offense = offensive_keys(lg, opp)
    assert bool(offense) == expected
    assert all("Value the ball" in key and "Their defense forces turnovers" in key for key in offense)
    assert guard_keys(lg, opp, {}, [], 15) == []
    if expected:
        assert lg.values["o.forced"] == "18.0"
        assert lg.values["o.forced_rank"] == report.ordinal(rank)


@pytest.mark.parametrize(
    "field,rank,expected",
    [
        ("orb_rank", 4, "box-out"),
        ("orb_rank", 5, ""),
        ("ft_rate_rank", 4, "Defend without fouling"),
        ("ft_rate_rank", 5, ""),
        ("tov_rank", 12, "Pressure the ball"),
        ("tov_rank", 11, ""),
    ],
)
def test_defensive_team_rules(field: str, rank: int, expected: str) -> None:
    opp = opponent(**{field: rank})
    defense = guard_keys(Ledger(), opp, {}, [], 15)
    assert len(defense) == bool(expected)
    assert not expected or expected in defense[0]
    assert offensive_keys(Ledger(), opp) == []


@pytest.mark.parametrize(
    "zone,rank,expected",
    [
        ("rim", 4, "Wall off the paint"),
        ("rim", 5, ""),
        ("3pt", 4, "Run them off the line"),
        ("3pt", 5, ""),
        ("mid", 13, "Concede the midrange"),
        ("mid", 12, ""),
    ],
)
def test_defensive_shot_rules(zone: str, rank: int, expected: str) -> None:
    shares = {zone: {"share_rank": rank, "share": 30}}
    defense = guard_keys(Ledger(), opponent(), shares, [], 15)
    assert len(defense) == bool(expected)
    assert not expected or expected in defense[0]


@pytest.mark.parametrize("share,expected", [(18, True), (17.9, False)])
def test_star_scoring_is_a_defensive_key(share: float, expected: bool) -> None:
    lg = Ledger()
    players = [{"name": "Scorer", "pts_share": share, "ppg": 20}]
    defense = guard_keys(lg, opponent(), {}, players, 15)
    assert bool(defense) == expected
    if expected:
        assert "Make Scorer work" in defense[0]
        assert lg.values["g.star_ppg"] == "20.0"


def test_independent_limits_and_transition_priority() -> None:
    opp = opponent(orb_rank=1, ft_rate_rank=1, tov_rank=15, opp_tov_rank=1)
    shares = {zone: {"share_rank": rank, "share": 30} for zone, rank in (("rim", 1), ("3pt", 1), ("mid", 15))}
    players = [{"name": "Scorer", "pts_share": 25, "ppg": 20}]
    stats = {"offense_rank": 4, "offense_share": 20}
    lg = Ledger()
    defense = guard_keys(lg, opp, shares, players, 15, stats)
    offense = offensive_keys(lg, opp)
    assert len(defense) == 3
    assert 0 < len(offense) <= 3
    assert "Get back early" in defense[0]
    assert all("Value the ball" not in key for key in defense)
    assert all("offensive glass" not in key and "avoid live-ball turnovers" not in key for key in defense)
    assert "Value the ball" in offense[0]
    assert not any("net" in key or "Don't let it get close late" in key for key in defense + offense)


@pytest.fixture
def fixture_reports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metrics, "CLEAN", FIXTURES / "good")


@pytest.mark.parametrize("abbr", ["ATL", "GS"])
def test_report_possession_sections(abbr: str, fixture_reports: None) -> None:
    result = report.compute(abbr, "2026-10-30")
    blocks = result["blocks"]
    assert ("h2", "How to guard them") not in blocks
    defense_idx = blocks.index(("h2", "When they have the ball"))
    offense_idx = blocks.index(("h2", "When we have the ball"))
    assert defense_idx < offense_idx < blocks.index(("h2", "Team profile"))
    kind, defense = blocks[defense_idx + 1]
    assert kind == "ol" and 1 <= len(defense) <= 3
    assert all("Value the ball" not in key for key in defense)
    kind, offense = blocks[offense_idx + 1]
    assert kind == "ol" and 1 <= len(offense) <= 3
    assert "Value the ball" in offense[0]
    assert ("h2", "Form and close games") in blocks


def test_report_no_defensive_keys_is_explicit(monkeypatch: pytest.MonkeyPatch, fixture_reports: None) -> None:
    monkeypatch.setattr(report, "guard_keys", lambda *args: [])
    blocks = report.compute("ATL", "2026-10-31")["blocks"]
    index = blocks.index(("h2", "When they have the ball"))
    assert blocks[index + 1] == ("p", "No standout defensive key is triggered by the current rules.")


def test_report_no_offensive_keys_is_explicit(monkeypatch: pytest.MonkeyPatch, fixture_reports: None) -> None:
    # Deterministically exercise a team outside the turnovers-forced threshold.
    team_table = metrics.team_table

    def no_turnover_edge(*args: Any) -> pd.DataFrame:
        teams = team_table(*args)
        teams["opp_tov_rank"] = 5
        return teams

    monkeypatch.setattr(metrics, "team_table", no_turnover_edge)
    blocks = report.compute("ATL", "2026-10-30")["blocks"]
    index = blocks.index(("h2", "When we have the ball"))
    assert blocks[index + 1] == ("p", "No standout offensive key is triggered by the current rules.")


def test_fixture_report_players_and_no_prior_meetings(monkeypatch: pytest.MonkeyPatch, fixture_reports: None) -> None:
    top_players = metrics.top_players
    # The fixture has only two games; render its real player rows in this case.
    monkeypatch.setattr(
        metrics, "top_players", lambda con, team_id, as_of: top_players(con, team_id, as_of, min_games=1)
    )
    monkeypatch.setattr(metrics, "head_to_head", lambda *args: [])
    result = report.compute("ATL", "2026-10-30")
    blocks = result["blocks"]
    assert result["ledger"]["p0.name"]
    index = blocks.index(("h2", "Head to head this season"))
    assert blocks[index + 1] == ("p", "No meetings yet this season.")


def test_qualifying_clutch_stats_do_not_add_a_key(monkeypatch: pytest.MonkeyPatch, fixture_reports: None) -> None:
    team_table = metrics.team_table
    transition = metrics.transition

    def neutral_team_table(*args: Any) -> pd.DataFrame:
        teams = team_table(*args)
        # A deterministic league context with no other qualifying team rules.
        for column, value in (("teams", 15), ("orb_rank", 5), ("ft_rate_rank", 5), ("tov_rank", 1)):
            teams[column] = value
        return teams

    def no_transition_edge(*args: Any) -> dict[str, Any]:
        return transition(*args) | {"offense_rank": 5}

    # The removed rule qualified at >= 5 games and >= +15 net.
    clutch = {"games": 5, "pts_for": 35, "pts_against": 15, "net": 20}
    monkeypatch.setattr(metrics, "clutch", lambda *args: clutch)
    monkeypatch.setattr(metrics, "team_table", neutral_team_table)
    monkeypatch.setattr(metrics, "transition", no_transition_edge)
    monkeypatch.setattr(metrics, "league_shot_shares", lambda *args: pd.DataFrame(columns=["team_id", "zone"]))
    result = report.compute("ATL", "2026-10-30")
    blocks = result["blocks"]
    defensive_index = blocks.index(("h2", "When they have the ball"))
    assert blocks[defensive_index + 1] == ("p", "No standout defensive key is triggered by the current rules.")
    assert "Don't let it get close late" not in report.to_markdown(blocks)
    form_index = blocks.index(("h2", "Form and close games"))
    kind, form = blocks[form_index + 1]
    assert kind == "ul"
    assert "Clutch time: 35 points scored, 15 allowed (+20) across 5 games." in form
    assert result["ledger"]["cl.net"] == "+20"

"""Scouting keys must describe the correct side of the ball."""

from typing import Any

import pandas as pd
import pytest

from scout import report
from scout.config import CLEAN
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


@pytest.mark.skipif(not (CLEAN / "team_box.parquet").exists(), reason="needs `make ingest`")
@pytest.mark.parametrize("abbr,as_of", [("ATL", "2026-10-31"), ("DAL", "2026-09-27")])
def test_report_possession_sections(abbr: str, as_of: str) -> None:
    result = report.compute(abbr, as_of)
    blocks = result["blocks"]
    assert ("h2", "How to guard them") not in blocks
    defense_idx = blocks.index(("h2", "When they have the ball"))
    offense_idx = blocks.index(("h2", "When we have the ball"))
    assert defense_idx < offense_idx < blocks.index(("h2", "Team profile"))
    kind, defense = blocks[defense_idx + 1]
    assert kind == "ol" and 1 <= len(defense) <= 3
    assert all("Value the ball" not in key for key in defense)
    kind, offense = blocks[offense_idx + 1]
    if abbr == "ATL":
        assert kind == "ol" and 1 <= len(offense) <= 3
        assert "Value the ball" in offense[0]
    else:
        assert (kind, offense) == ("p", "No standout offensive key is triggered by the current rules.")
    assert ("h2", "Form and close games") in blocks


@pytest.mark.skipif(not (CLEAN / "team_box.parquet").exists(), reason="needs `make ingest`")
def test_report_no_defensive_keys_is_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(report, "guard_keys", lambda *args: [])
    blocks = report.compute("ATL", "2026-10-31")["blocks"]
    index = blocks.index(("h2", "When they have the ball"))
    assert blocks[index + 1] == ("p", "No standout defensive key is triggered by the current rules.")

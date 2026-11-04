"""Opponent scouting report for the Valkyries.

    python -m scout.report --opponent ATL                     # next scheduled GS vs ATL game
    python -m scout.report --opponent DAL --as-of 2026-09-27  # replay: as if prepping for that date

Writes reports/<OPP>_<date>.md, .pdf and .ledger.json.
Every number in the report goes through `Ledger.num`, so `scout.check_report`
can prove the text contains no number that was not computed from data.
"""
import argparse
import json
import sys
from datetime import date

from scout import metrics as m
from scout.config import CLIENT_ABBR, CLIENT_TEAM_ID, REPORTS


def ordinal(n):
    n = int(n)
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


class Ledger:
    """Records every printed value under a stable key."""

    def __init__(self):
        self.values = {}

    def num(self, key, value, fmt="{:.1f}"):
        text = fmt.format(value)
        self.values[key] = text
        return text

    def rank(self, key, value):
        text = ordinal(value)
        self.values[key] = text
        return text

    def text(self, key, value):
        self.values[key] = str(value)
        return str(value)


def find_game(con, opp_id, as_of=None):
    """The next unplayed GS vs opponent game on the schedule, or the as_of date given."""
    if as_of:
        row = con.execute(
            "SELECT game_date, notes_headline FROM schedule WHERE game_date = ? "
            "AND ? IN (home_id, away_id) AND ? IN (home_id, away_id)",
            [as_of, CLIENT_TEAM_ID, opp_id]).fetchone()
        return as_of, (row[1] if row and row[1] else "Regular season game")
    row = con.execute(
        "SELECT game_date, notes_headline FROM schedule WHERE NOT status_type_completed "
        "AND ? IN (home_id, away_id) AND ? IN (home_id, away_id) ORDER BY game_date LIMIT 1",
        [CLIENT_TEAM_ID, opp_id]).fetchone()
    if row:
        return row[0].isoformat(), row[1] or "Next matchup"
    return date.today().isoformat(), "Next matchup"


def guard_keys(L, opp, gs_shots, shares, players, cl, n_teams):
    """Rule-based 'how to guard them' points. Each has an extremity score; the top 3 are used."""
    cands = []
    rim = shares.get("rim")
    three = shares.get("3pt")
    mid = shares.get("mid")
    if rim is not None and rim["share_rank"] <= 4:
        cands.append((5 - rim["share_rank"],
            f"Wall off the paint. {L.num('g.rim_share', rim['share'])}% of their shots come at the rim "
            f"({L.rank('g.rim_rank', rim['share_rank'])} of {L.num('g.n1', n_teams, '{:.0f}')} in the league)."))
    if three is not None and three["share_rank"] <= 4:
        cands.append((5 - three["share_rank"],
            f"Run them off the line. {L.num('g.three_share', three['share'])}% of their shots are threes "
            f"({L.rank('g.three_rank', three['share_rank'])} of {L.num('g.n2', n_teams, '{:.0f}')})."))
    if mid is not None and mid["share_rank"] >= n_teams - 2:
        cands.append((mid["share_rank"] - (n_teams - 3),
            f"Concede the midrange. Only {L.num('g.mid_share', mid['share'])}% of their shots are midrange twos "
            f"({L.rank('g.mid_rank', mid['share_rank'])} of {L.num('g.n3', n_teams, '{:.0f}')}); "
            f"force them there."))
    if opp["orb_rank"] <= 4:
        cands.append((5 - opp["orb_rank"],
            f"Finish every possession with a box-out. They rebound {L.num('g.orb', opp['orb_pct'])}% of their misses "
            f"({L.rank('g.orb_rank', opp['orb_rank'])})."))
    if opp["ft_rate_rank"] <= 4:
        cands.append((5 - opp["ft_rate_rank"],
            f"Defend without fouling. Their free-throw rate is {L.num('g.ftr', opp['ft_rate'])} "
            f"({L.rank('g.ftr_rank', opp['ft_rate_rank'])})."))
    if opp["tov_rank"] >= n_teams - 3:
        cands.append((opp["tov_rank"] - (n_teams - 4),
            f"Pressure the ball. They turn it over on {L.num('g.tov', opp['tov_pct'])}% of possessions "
            f"({L.rank('g.tov_rank', opp['tov_rank'])} in ball security)."))
    if opp["opp_tov_rank"] <= 4:
        cands.append((5 - opp["opp_tov_rank"],
            f"Value the ball. Their defense forces turnovers on {L.num('g.forced', opp['opp_tov_pct'])}% of "
            f"possessions ({L.rank('g.forced_rank', opp['opp_tov_rank'])})."))
    if players and players[0]["pts_share"] >= 18:
        p = players[0]
        cands.append((3,
            f"Make {L.text('g.star', p['name'])} work. She scores {L.num('g.star_ppg', p['ppg'])} a game, "
            f"{L.num('g.star_share', p['pts_share'])}% of their points."))
    if cl["games"] >= 5 and cl["net"] >= 15:
        cands.append((2,
            f"Don't let it get close late. They are {L.num('g.clutch_net', cl['net'], '{:+.0f}')} in clutch "
            f"time across {L.num('g.clutch_games', cl['games'], '{:.0f}')} close games."))
    cands.sort(key=lambda c: -c[0])
    return [c[1] for c in cands[:3]]


def compute(opponent, as_of=None):
    con = m.connect()
    opp_id, opp_name = m.team_id_for(con, opponent)
    game_date, headline = find_game(con, opp_id, as_of)
    L = Ledger()
    blocks = []

    teams = m.team_table(con, game_date)
    n = int(teams["teams"].iloc[0])
    opp = teams[teams.team_id == opp_id].iloc[0]
    gs = teams[teams.team_id == CLIENT_TEAM_ID].iloc[0]
    last = con.execute("SELECT max(game_date) FROM team_box WHERE game_date < ?", [game_date]).fetchone()[0]
    shares_df = m.league_shot_shares(con, game_date)
    shares = {r["zone"]: r for r in shares_df[shares_df.team_id == opp_id].to_dict("records")}
    off = m.shot_profile(con, opp_id, game_date, "offense")
    dfn = m.shot_profile(con, opp_id, game_date, "defense")
    players = m.top_players(con, opp_id, game_date)
    cl = m.clutch(con, opp_id, game_date)
    form = m.recent_form(con, opp_id, game_date)
    h2h = m.head_to_head(con, CLIENT_TEAM_ID, opp_id, game_date)

    blocks.append(("h1", f"Scouting report: {L.text('opp.name', opp_name)}"))
    blocks.append(("p", f"For Golden State Valkyries basketball ops. Game: {L.text('game.headline', headline)}, "
                        f"{L.text('game.date', game_date)}. Built from public data through "
                        f"{L.text('data.last', last.isoformat())} "
                        f"({L.num('opp.games', opp['games'], '{:.0f}')} {opp['abbr']} games, regular season and playoffs)."))

    blocks.append(("h2", "How to guard them"))
    blocks.append(("ol", guard_keys(L, opp, None, shares, players, cl, n)))

    blocks.append(("h2", "Team profile"))
    blocks.append(("p", f"Record {L.num('opp.w', opp['wins'], '{:.0f}')}-{L.num('opp.l', opp['losses'], '{:.0f}')}, "
                        f"net rating {L.num('opp.net', opp['net'], '{:+.1f}')} "
                        f"({L.rank('opp.net_rank', opp['net_rank'])} of {L.num('n.teams', n, '{:.0f}')}). "
                        f"Ranks: {L.rank('static.best', 1)} is best."))
    rows = [["", f"{opp['abbr']}", "Rank", CLIENT_ABBR, "Rank"]]
    spec = [("Offensive rating", "ortg", "ortg_rank"), ("Defensive rating", "drtg", "drtg_rank"),
            ("Pace", "pace", "pace_rank"), ("eFG%", "efg", "efg_rank"),
            ("Turnover %", "tov_pct", "tov_rank"), ("Off. rebound %", "orb_pct", "orb_rank"),
            ("FT rate", "ft_rate", "ft_rate_rank"), ("3PA rate", "three_rate", "three_rate_rank"),
            ("Opp. eFG% allowed", "opp_efg", "opp_efg_rank"), ("Turnovers forced %", "opp_tov_pct", "opp_tov_rank")]
    for label, col, rcol in spec:
        rows.append([label, L.num(f"opp.{col}", opp[col]), L.rank(f"opp.{rcol}", opp[rcol]),
                     L.num(f"gs.{col}", gs[col]), L.rank(f"gs.{rcol}", gs[rcol])])
    blocks.append(("table", rows))

    blocks.append(("h2", "Shot profile"))
    rows = [["Zone", "Share of their shots", "Their FG%", "Share allowed", "FG% allowed"]]
    names = {"rim": "Rim", "mid": "Midrange", "3pt": "Three"}
    for z in ("rim", "mid", "3pt"):
        rows.append([names[z], L.num(f"off.{z}.share", off[z]["share"]) + "%", L.num(f"off.{z}.fg", off[z]["fg_pct"]) + "%",
                     L.num(f"def.{z}.share", dfn[z]["share"]) + "%", L.num(f"def.{z}.fg", dfn[z]["fg_pct"]) + "%"])
    blocks.append(("table", rows))

    blocks.append(("h2", "Players to plan for"))
    rows = [["Player", "PPG", "RPG", "APG", "TS%", "3PA/G", "3P%", "Share of team pts"]]
    for i, p in enumerate(players):
        rows.append([L.text(f"p{i}.name", p["name"]), L.num(f"p{i}.ppg", p["ppg"]), L.num(f"p{i}.rpg", p["rpg"]),
                     L.num(f"p{i}.apg", p["apg"]), L.num(f"p{i}.ts", p["ts_pct"]), L.num(f"p{i}.tpa", p["tpa_pg"]),
                     L.num(f"p{i}.3p", p["three_pct"] or 0), L.num(f"p{i}.share", p["pts_share"]) + "%"])
    blocks.append(("table", rows))

    blocks.append(("h2", "Form and close games"))
    blocks.append(("ul", [
        f"Last {L.num('form.games', form['games'], '{:.0f}')} games: {L.num('form.w', form['wins'], '{:.0f}')}-"
        f"{L.num('form.l', form['losses'], '{:.0f}')}, net rating {L.num('form.net', form['net'], '{:+.1f}')}.",
        f"Clutch time: {L.num('cl.for', cl['pts_for'], '{:.0f}')} points scored, "
        f"{L.num('cl.against', cl['pts_against'], '{:.0f}')} allowed "
        f"({L.num('cl.net', cl['net'], '{:+.0f}')}) across {L.num('cl.games', cl['games'], '{:.0f}')} games.",
    ]))

    blocks.append(("h2", "Head to head this season"))
    if h2h:
        wins = sum(1 for g in h2h if g["win"])
        blocks.append(("p", f"Valkyries are {L.num('h2h.w', wins, '{:.0f}')}-{L.num('h2h.l', len(h2h) - wins, '{:.0f}')} "
                            f"against {opp['abbr']}."))
        rows = [["Date", "Type", CLIENT_ABBR, opp["abbr"], "Result"]]
        for i, g in enumerate(h2h):
            rows.append([L.text(f"h2h{i}.date", g["game_date"].date().isoformat()),
                         "Playoffs" if g["season_type"] == 3 else "Regular",
                         L.num(f"h2h{i}.pts", g["pts"], "{:.0f}"), L.num(f"h2h{i}.opp", g["opp_pts"], "{:.0f}"),
                         "W" if g["win"] else "L"])
        blocks.append(("table", rows))
    else:
        blocks.append(("p", "No meetings yet this season."))

    blocks.append(("h2", "Definitions"))
    blocks.append(("p", f"Possessions = FGA - ORB + TOV + {L.num('def.ftw', 0.44, '{:.2f}')} x FTA. Ratings are points "
                        f"per {L.num('def.per', 100, '{:.0f}')} possessions. Rim = layups, dunks, tips and putbacks. "
                        f"Clutch = final {L.num('def.clutch_min', 5, '{:.0f}')} minutes of the {L.rank('def.q4', 4)} quarter or overtime "
                        f"with the score within {L.num('def.clutch_margin', 5, '{:.0f}')}. Source: ESPN data via "
                        f"SportsDataverse (public)."))
    return {"opponent": opp["abbr"], "game_date": game_date, "blocks": blocks, "ledger": L.values}


def to_markdown(blocks):
    out = []
    for kind, body in blocks:
        if kind == "h1":
            out.append(f"# {body}\n")
        elif kind == "h2":
            out.append(f"## {body}\n")
        elif kind == "p":
            out.append(f"{body}\n")
        elif kind == "ol":
            out.append("\n".join(f"{i + 1}. {t}" for i, t in enumerate(body)) + "\n")
        elif kind == "ul":
            out.append("\n".join(f"- {t}" for t in body) + "\n")
        elif kind == "table":
            head, *rest = body
            out.append("| " + " | ".join(head) + " |\n|" + "---|" * len(head) + "\n" +
                       "\n".join("| " + " | ".join(r) + " |" for r in rest) + "\n")
    return "\n".join(out)


def to_pdf(blocks, path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    ss = getSampleStyleSheet()
    gold, purple = colors.HexColor("#E8B21F"), colors.HexColor("#3B1E6E")
    story = []
    for kind, body in blocks:
        if kind == "h1":
            story += [Paragraph(body, ss["Title"]), Spacer(1, 4)]
        elif kind == "h2":
            story += [Spacer(1, 8), Paragraph(body, ss["Heading2"])]
        elif kind == "p":
            story.append(Paragraph(body, ss["BodyText"]))
        elif kind in ("ol", "ul"):
            story.append(ListFlowable([ListItem(Paragraph(t, ss["BodyText"])) for t in body],
                                      bulletType="1" if kind == "ol" else "bullet"))
        elif kind == "table":
            t = Table(body, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), purple), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F6F1E3")]),
                ("LINEBELOW", (0, 0), (-1, 0), 1.2, gold)]))
            story.append(t)
    SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                      topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                      title="Scouting report").build(story)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--opponent", required=True, help="team abbreviation, e.g. ATL")
    ap.add_argument("--as-of", help="YYYY-MM-DD; use only games before this date")
    ap.add_argument("--no-pdf", action="store_true")
    args = ap.parse_args(argv)
    r = compute(args.opponent, args.as_of)
    REPORTS.mkdir(exist_ok=True)
    stem = REPORTS / f"{r['opponent']}_{r['game_date']}"
    stem.with_suffix(".md").write_text(to_markdown(r["blocks"]))
    stem.with_suffix(".ledger.json").write_text(json.dumps(
        {"opponent": r["opponent"], "game_date": r["game_date"], "values": r["ledger"]}, indent=2))
    if not args.no_pdf:
        to_pdf(r["blocks"], stem.with_suffix(".pdf"))
    print(stem.with_suffix(".md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())

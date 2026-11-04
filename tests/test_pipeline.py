import shutil

import duckdb
import pytest

from scout import validate
from scout.check_report import tokens
from scout.config import CLEAN, FIXTURES
from scout.report import ordinal

GOOD = FIXTURES / "good"


def _copy(tmp_path):
    for f in GOOD.glob("*.parquet"):
        shutil.copy(f, tmp_path / f.name)
    return tmp_path


def _rewrite(path, select_sql):
    con = duckdb.connect()
    tmp = path.with_suffix(".tmp.parquet")
    con.execute(f"COPY ({select_sql.format(src=path)}) TO '{tmp}' (FORMAT parquet)")
    tmp.replace(path)


def failed(results):
    return {r.name for r in results if not r.ok}


def test_fixture_passes_all_checks():
    assert failed(validate.run(GOOD)) == set()


def test_renamed_column_fails_contract(tmp_path):
    d = _copy(tmp_path)
    p = d / "pbp.parquet"
    _rewrite(p, "SELECT * RENAME (score_value AS scoreValue) FROM '{src}'")
    bad = failed(validate.run(d))
    assert "contract:pbp" in bad


def test_score_mismatch_fails_invariant(tmp_path):
    d = _copy(tmp_path)
    p = d / "team_box.parquet"
    _rewrite(p, "SELECT * REPLACE (team_score + 2 AS team_score) FROM '{src}'")
    bad = failed(validate.run(d))
    assert "pbp:points_match_box" in bad
    assert "team_box:points_add_up" in bad


def test_duplicate_rows_fail(tmp_path):
    d = _copy(tmp_path)
    p = d / "team_box.parquet"
    _rewrite(p, "SELECT * FROM '{src}' UNION ALL SELECT * FROM '{src}' LIMIT 5")
    assert "team_box:unique_team_game" in failed(validate.run(d))


def test_ordinals():
    assert [ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21)] == \
        ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st"]


def test_number_scanner_ignores_labels_and_list_markers():
    text = "1. Shot 42.7% (2nd of 15). 3PA rate and eFG% are labels. Net +6.5 on 2026-10-29."
    assert tokens(text) == ["2026-10-29", "42.7", "2nd", "15", "+6.5"]


@pytest.mark.skipif(not (CLEAN / "team_box.parquet").exists(), reason="needs `make ingest`")
def test_full_report_passes_number_check(tmp_path, monkeypatch):
    from scout import report
    from scout.check_report import check
    monkeypatch.setattr(report, "REPORTS", tmp_path)
    report.main(["--opponent", "ATL", "--as-of", "2026-10-29", "--no-pdf"])
    md = next(tmp_path.glob("*.md"))
    assert check(md) == []

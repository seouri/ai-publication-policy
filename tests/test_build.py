import json
import shutil
from pathlib import Path

import pytest
import yaml

from ai_publication_policy.build import DataError, build, load_nodes

DATA = Path(__file__).parent.parent / "data"


def payload(html: str) -> dict:
    start = html.index("const DATA = ") + len("const DATA = ")
    end = html.index(";\nconst N = DATA.nodes")
    return json.loads(html[start:end].replace("<\\/", "</"))


@pytest.fixture
def data_copy(tmp_path):
    shutil.copytree(DATA, tmp_path / "data")
    return tmp_path / "data"


def edit(path: Path, fn):
    doc = yaml.safe_load(path.read_text())
    fn(doc)
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False))


def test_shipped_data_builds():
    data = payload(build(DATA))
    tiers = {n["c"] for n in data["nodes"]}
    assert tiers == {0, 1, 2, 3}
    assert len(data["columns"]) == 5


def test_nodes_keep_tier_order():
    columns = [n["c"] for n in load_nodes(DATA)]
    assert columns == sorted(columns)


def test_new_journal_appears_under_its_publisher(data_copy):
    def add(doc):
        pub = next(p for p in doc["publishers"] if p["id"] == "els")
        pub["journals"].append({"id": "newj", "name": "New Journal", "strictness": 3, "vs_parent": "same",
                                "url": "https://example.org", "verdict": "Standard.", "rules": ["See Elsevier"]})
    edit(data_copy / "publishers.yaml", add)
    node = next(n for n in payload(build(data_copy))["nodes"] if n["id"] == "newj")
    assert node["p"] == "els" and node["d"] == "=" and node["tier"] == "Journal"


@pytest.mark.parametrize("mutate, message", [
    (lambda d: d["publishers"][0]["journals"][0].update(cites=["nope"]), "cites unknown id"),
    (lambda d: d["publishers"][0]["journals"][0].update(strictness=9), "strictness must be 1-5"),
    (lambda d: d["publishers"][0]["journals"][0].update(vs_parent="worse"), "vs_parent must be one of"),
    (lambda d: d["publishers"][0]["journals"][0].update(id=d["publishers"][1]["id"]), "duplicate id"),
    (lambda d: d["publishers"][0].update(journals=[]), "needs at least one journal"),
    (lambda d: d["publishers"][0]["journals"][0].pop("verdict"), "missing required field"),
])
def test_bad_data_is_rejected(data_copy, mutate, message):
    edit(data_copy / "publishers.yaml", mutate)
    with pytest.raises(DataError, match=message):
        build(data_copy)


def test_bad_matrix_score_is_rejected(data_copy):
    edit(data_copy / "matrix.yaml", lambda d: d["groups"][0]["rows"][0].update(disc=[7, "x"]))
    with pytest.raises(DataError, match="score must be 1-4"):
        build(data_copy)


def test_standalone_page_is_a_full_document():
    html = build(DATA, standalone=True)
    assert html.startswith("<!doctype html>")
    assert '<meta name="viewport"' in html and html.rstrip().endswith("</html>")
    assert not build(DATA).startswith("<!doctype")


def test_survey_date_comes_from_data_not_build_day():
    html = build(DATA)
    day = yaml.safe_load((DATA / "survey.yaml").read_text())["last_surveyed"]
    assert f'<time datetime="{day.isoformat()}">' in html
    assert "<!--@SURVEYED@-->" not in html


@pytest.mark.parametrize("value", ["October 2026", "2026-10", "2026-10-23T09:00:00"])
def test_survey_date_must_be_a_day(data_copy, value):
    (data_copy / "survey.yaml").write_text(f"last_surveyed: {value}\n")
    with pytest.raises(DataError, match="last_surveyed"):
        build(data_copy)


def test_matrix_rows_link_to_nodes(data_copy):
    scores = payload(build(DATA))["scores"]
    assert scores["els"]["row"] == "Elsevier" and len(scores["els"]["cells"]) == 5
    edit(data_copy / "matrix.yaml", lambda d: d["groups"][0]["rows"][0].update(nodes=["nope"]))
    with pytest.raises(DataError, match="unknown id 'nope'"):
        build(data_copy)


def test_score_cannot_exceed_column_levels(data_copy):
    def bad(d):
        d["groups"][0]["rows"][0]["gram"] = [4, "x"]  # gram has three levels
    edit(data_copy / "matrix.yaml", bad)
    with pytest.raises(DataError, match="score must be 1-3"):
        build(data_copy)

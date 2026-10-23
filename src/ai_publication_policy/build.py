"""Render the AI policy cascade page from the YAML files in data/."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from importlib.resources import files
from pathlib import Path

import yaml

DELTA = {"same": "=", "stricter": "▲", "looser": "▼", "inconsistent": "≠", "unverified": "⚠"}
DEFAULT_TIER = {0: "Cross-publisher framework", 1: "Publisher", 2: "Journal", 3: "Article-type rule"}
NODE_FIELDS = {
    "id", "name", "sub", "strictness", "vs_parent", "tier", "date", "url",
    "verdict", "rules", "note", "cites", "weak_cites", "journals", "article_rules",
}
REQUIRED = ("id", "name", "verdict", "rules", "url")
MARKER = "/*@DATA@*/null"
SURVEY_MARKER = "<!--@SURVEYED@-->"

# template.html is a page body for hosts that supply their own document shell (Claude artifacts).
# For a standalone site (GitHub Pages) it gets wrapped in this shell instead.
DESCRIPTION = (
    "How generative-AI policies for manuscript preparation cascade from ICMJE and COPE "
    "through publishers to journals and article types, with a strictness matrix."
)
SHELL_HEAD = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{DESCRIPTION}">
<meta property="og:title" content="AI Policy Cascade">
<meta property="og:description" content="{DESCRIPTION}">
<meta property="og:type" content="website">
<style>
:root {{ color-scheme: light; padding-top: env(safe-area-inset-top, 0px); padding-bottom: env(safe-area-inset-bottom, 0px); }}
body {{ margin: 0; font: 14px system-ui, -apple-system, "Segoe UI", sans-serif; }}
img {{ max-width: 100%; }}
[hidden] {{ display: none !important; }}
</style>
"""
SHELL_TAIL = "\n</body>\n</html>\n"


class DataError(Exception):
    pass


def _load(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        raise DataError(f"missing data file: {path}") from None


def _node(raw: dict, column: int, parent: str | None, where: str) -> dict:
    unknown = set(raw) - NODE_FIELDS
    if unknown:
        raise DataError(f"{where}: unknown field(s) {sorted(unknown)}")
    for key in REQUIRED:
        if not raw.get(key):
            raise DataError(f"{where}: missing required field '{key}'")
    s = raw.get("strictness")
    if s is not None and s not in range(1, 6):
        raise DataError(f"{where}: strictness must be 1-5 or null, got {s!r}")
    node = {
        "id": raw["id"], "c": column, "name": raw["name"], "s": s,
        "tier": raw.get("tier", DEFAULT_TIER[column]),
        "url": raw["url"], "verdict": raw["verdict"], "rules": list(raw["rules"]),
    }
    if parent:
        node["p"] = parent
    if "vs_parent" in raw:
        if raw["vs_parent"] not in DELTA:
            raise DataError(f"{where}: vs_parent must be one of {sorted(DELTA)}")
        node["d"] = DELTA[raw["vs_parent"]]
    for src, dst in (("sub", "sub"), ("date", "date"), ("note", "note"), ("cites", "parents"), ("weak_cites", "weak")):
        if raw.get(src):
            node[dst] = raw[src]
    return node


def load_nodes(data_dir: Path) -> list[dict]:
    frameworks = _load(data_dir / "frameworks.yaml").get("frameworks", [])
    publishers = _load(data_dir / "publishers.yaml").get("publishers", [])
    nodes = [_node(f, 0, None, f"frameworks[{f.get('id', i)}]") for i, f in enumerate(frameworks)]
    journals, rules = [], []
    for pub in publishers:
        pid = pub.get("id")
        nodes.append(_node({k: v for k, v in pub.items() if k != "journals"}, 1, None, f"publishers[{pid}]"))
        for j in pub.get("journals") or []:
            jid = j.get("id")
            journals.append(_node({k: v for k, v in j.items() if k != "article_rules"}, 2, pid, f"{pid}.journals[{jid}]"))
            for a in j.get("article_rules") or []:
                rules.append(_node(a, 3, jid, f"{pid}.{jid}.article_rules[{a.get('id')}]"))
    nodes += journals + rules

    ids = [n["id"] for n in nodes]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise DataError(f"duplicate id(s): {sorted(dupes)}")
    by_id = {n["id"]: n for n in nodes}
    for n in nodes:
        for cited in n.get("parents", []) + n.get("weak", []):
            if cited not in by_id:
                raise DataError(f"{n['id']}: cites unknown id '{cited}'")
            if by_id[cited]["c"] >= n["c"]:
                raise DataError(f"{n['id']}: can only cite a node in an earlier tier, not '{cited}'")
        if set(n.get("weak", [])) - set(n.get("parents", [])):
            raise DataError(f"{n['id']}: every weak_cites id must also be in cites")
    for p in (n for n in nodes if n["c"] == 1):
        if not any(j.get("p") == p["id"] for j in journals):
            raise DataError(f"publisher '{p['id']}' needs at least one journal (it is positioned by its journals)")
    return nodes


def load_matrix(data_dir: Path) -> tuple[list, list]:
    raw = _load(data_dir / "matrix.yaml")
    columns = raw.get("columns", [])
    keys = [c["key"] for c in columns]
    out = []
    for g in raw.get("groups", []):
        out.append([g["group"]])
        for row in g.get("rows", []):
            where = f"matrix[{g['group']}/{row.get('name')}]"
            extra = set(row) - {"name", "sub", *keys}
            if extra:
                raise DataError(f"{where}: unknown column(s) {sorted(extra)}")
            cells = []
            for k in keys:
                cell = row.get(k, [None, "Not stated"])
                if not (isinstance(cell, list) and len(cell) == 2):
                    raise DataError(f"{where}.{k}: cell must be [score, text]")
                if cell[0] is not None and cell[0] not in range(1, 5):
                    raise DataError(f"{where}.{k}: score must be 1-4 or null")
                cells.append(cell)
            out.append([row["name"], row.get("sub", ""), *cells])
    return [[c["key"], c["label"], c.get("hint", "")] for c in columns], out


def load_survey_date(data_dir: Path) -> dt.date:
    """The day sources were last rechecked. Set by hand in data/survey.yaml, never from the build clock."""
    raw = _load(data_dir / "survey.yaml").get("last_surveyed")
    if not isinstance(raw, dt.date) or isinstance(raw, dt.datetime):
        raise DataError("survey.yaml: last_surveyed must be a date written as YYYY-MM-DD")
    return raw


def _survey_html(day: dt.date) -> str:
    return f'<time datetime="{day.isoformat()}">{day.day} {day:%b %Y}</time>'


def build(data_dir: Path, standalone: bool = False) -> str:
    nodes = load_nodes(data_dir)
    columns, matrix = load_matrix(data_dir)
    template = files("ai_publication_policy").joinpath("template.html").read_text(encoding="utf-8")
    if MARKER not in template:
        raise DataError("template.html is missing the data marker")
    payload = json.dumps({"nodes": nodes, "columns": columns, "matrix": matrix}, ensure_ascii=False, indent=1)
    # Keep "</script>" inside a string from closing the page's script element.
    payload = payload.replace("</", "<\\/")
    if SURVEY_MARKER not in template:
        raise DataError("template.html is missing the survey-date marker")
    page = template.replace(MARKER, payload).replace(SURVEY_MARKER, _survey_html(load_survey_date(data_dir)))
    if not standalone:
        return page
    # The template's leading <title>, <link> and <style> belong in <head>; the rest is the body.
    split = page.index('<div class="wrap">')
    return SHELL_HEAD + page[:split] + "</head>\n<body>\n" + page[split:] + SHELL_TAIL


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"), help="directory holding the YAML files")
    parser.add_argument("--out", type=Path, default=Path("dist/index.html"), help="where to write the page")
    parser.add_argument("--fragment", action="store_true",
                        help="omit the <html>/<head> shell, for hosts that add their own (Claude artifacts)")
    parser.add_argument("--check", action="store_true", help="validate the data without writing the page")
    args = parser.parse_args(argv)
    try:
        html = build(args.data, standalone=not args.fragment)
    except DataError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    if args.check:
        print("data OK")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0

from pathlib import Path

import yaml

from ai_publication_policy.sources import extract, norm_url, parse_saved, todo

BLOCKED = {"pages": [
    {"url": "https://www.science.org/content/page/science-journals-editorial-policies", "for": "Science", "why": "x"},
    {"url": "https://www.nature.com/nature/editorial-policies/ai", "for": "Nature", "why": "x"},
]}
POLICY = "<p>Artificial intelligence (AI). AI-assisted technologies do not meet the criteria for authorship and must be disclosed.</p>"


def setup(tmp_path: Path) -> tuple[Path, Path]:
    blocked = tmp_path / "blocked.yaml"
    blocked.write_text(yaml.safe_dump(BLOCKED))
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    return inbox, blocked


def test_norm_url_ignores_scheme_www_query_and_slash():
    assert norm_url("https://www.Science.org/a/b/?x=1#y") == norm_url("http://science.org/a/b")


def test_url_from_canonical_comment_or_self_link(tmp_path):
    canon = tmp_path / "a.html"
    canon.write_text(f'<link rel="canonical" href="https://www.science.org/content/page/science-journals-editorial-policies">{POLICY}')
    comment = tmp_path / "b.html"
    comment.write_text(f"<!-- saved from url=(0049)https://www.nature.com/nature/editorial-policies/ai -->{POLICY}")
    selflink = tmp_path / "c.html"
    selflink.write_text(f'<nav><a href="/nature/editorial-policies/ai">AI</a></nav>{POLICY}')
    known = [p["url"] for p in BLOCKED["pages"]]
    assert "science.org" in parse_saved(canon)["url"]
    assert "nature.com" in parse_saved(comment)["url"]
    assert "nature.com" in parse_saved(selflink, known)["url"]


def test_bot_check_page_is_rejected(tmp_path):
    f = tmp_path / "x.html"
    f.write_text("<title>Just a moment...</title><p>Enable JavaScript and cookies to continue</p>")
    assert parse_saved(f)["challenge"]


def test_extract_writes_text_and_reports_missing(tmp_path, capsys):
    inbox, blocked = setup(tmp_path)
    (inbox / "Science.html").write_text(
        f'<link rel="canonical" href="https://www.science.org/content/page/science-journals-editorial-policies"><title>Policies</title>{POLICY}')
    assert extract(inbox, blocked) == 0
    out = (inbox / "extracted" / "science-org-content-page-science-journals-editorial-policies.txt").read_text()
    assert "Listed in blocked.yaml: yes - Science" in out and "AI-assisted technologies" in out
    assert "still needed: https://www.nature.com/nature/editorial-policies/ai" in capsys.readouterr().out


def test_extract_fails_on_bot_check_and_todo_skips_saved(tmp_path, capsys):
    inbox, blocked = setup(tmp_path)
    (inbox / "bad.html").write_text("<title>Just a moment...</title>")
    assert extract(inbox, blocked) == 1
    (inbox / "ok.html").write_text(f'<meta property="og:url" content="https://www.nature.com/nature/editorial-policies/ai">{POLICY}')
    capsys.readouterr()
    todo(False, inbox, blocked)
    out = capsys.readouterr().out
    assert "science.org" in out and "nature.com" not in out

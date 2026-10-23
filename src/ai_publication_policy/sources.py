"""Collect policy pages that block automated retrieval, via one manual browser save each.

    uv run sources todo [--open]   list (and open) the pages still to save
    uv run sources extract         turn saved pages in sources/inbox/ into text
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import re
import shutil
import sys
import webbrowser
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

import yaml

BLOCKED = Path("sources/blocked.yaml")
INBOX = Path("sources/inbox")
SAVED_TYPES = {".html", ".htm", ".pdf"}
KEYWORDS = re.compile(
    r"artificial intelligence|generative|large language|\bLLMs?\b|\bAI\b|chatbot|ChatGPT|machine[- ]generated",
    re.IGNORECASE,
)
CHALLENGE = re.compile(
    r"just a moment|enable javascript and cookies|verify you are human|checking your browser|access denied|attention required",
    re.IGNORECASE,
)
BLOCK_TAGS = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "td", "th", "dd", "dt"}


def norm_url(url: str) -> str:
    """Compare URLs by host and path only (no scheme, www, query, fragment or trailing slash)."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().removeprefix("www.")
    return f"{host}{parts.path.rstrip('/')}"


class _Page(HTMLParser):
    """Text and source URL of a saved page. Parses only; never runs anything."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title, self.canonical, self.og_url, self.saved_from = "", "", "", ""
        self.hrefs: list[str] = []
        self._chunks: list[str] = []
        self._skip = 0
        self._in_title = False

    def handle_comment(self, data: str) -> None:
        # Chrome and Edge stamp saved pages with: <!-- saved from url=(0047)https://… -->
        m = re.search(r"saved from url=\(\d+\)(\S+)", data)
        if m and not self.saved_from:
            self.saved_from = m.group(1)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag in ("script", "style", "noscript", "svg", "template"):
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = self.canonical or a.get("href", "")
        elif tag in ("a", "base") and a.get("href"):
            self.hrefs.append(a["href"])
        elif tag == "meta" and a.get("property", "").lower() == "og:url":
            self.og_url = self.og_url or a.get("content", "")
        if tag in BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "svg", "template") and self._skip:
            self._skip -= 1
        elif tag == "title":
            self._in_title = False
        if tag in BLOCK_TAGS:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._chunks.append(data)

    @property
    def text(self) -> str:
        lines = (re.sub(r"[ \t ]+", " ", line).strip() for line in "".join(self._chunks).splitlines())
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()

    @property
    def url(self) -> str:
        return next((u for u in (self.canonical, self.og_url, self.saved_from) if u.startswith("http")), "")


def load_blocked(path: Path = BLOCKED) -> list[dict]:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("pages", [])


def _guess_url(page: _Page, known: list[str]) -> str:
    """For pages without URL metadata: a known blocked URL the page links to (nav, breadcrumbs, language switch)."""
    paths = {urlsplit(h).path.rstrip("/") for h in page.hrefs}
    full = {norm_url(h) for h in page.hrefs if h.startswith("http")}
    matches = [u for u in known if norm_url(u) in full or urlsplit(u).path.rstrip("/") in paths]
    return matches[0] if len(matches) == 1 else ""


def parse_saved(path: Path, known: list[str] | None = None) -> dict:
    """Read one saved page: its source URL, title, text, and whether it is a bot-check page."""
    page = _Page()
    page.feed(path.read_text(encoding="utf-8", errors="replace"))
    text = page.text
    title = html.unescape(page.title).strip()
    challenge = bool(CHALLENGE.search(title)) or (len(text) < 1500 and bool(CHALLENGE.search(text)))
    url = page.url or _guess_url(page, known or [])
    return {"url": url, "title": title, "text": text, "challenge": challenge}


def excerpts(text: str, limit: int = 60) -> list[str]:
    paras = [p for p in re.split(r"\n\s*\n|\n", text) if len(p) > 40]
    return [p for p in paras if KEYWORDS.search(p)][:limit]


def _slug(url: str, fallback: str) -> str:
    base = norm_url(url) if url else fallback
    return re.sub(r"[^A-Za-z0-9]+", "-", base).strip("-").lower()[:120] or "page"


def extract(inbox: Path = INBOX, blocked: Path = BLOCKED) -> int:
    out_dir = inbox / "extracted"
    out_dir.mkdir(parents=True, exist_ok=True)
    wanted = {norm_url(p["url"]): p for p in load_blocked(blocked)}
    got: set[str] = set()
    problems = 0
    saved = sorted(f for f in inbox.iterdir() if f.is_file() and f.suffix.lower() in SAVED_TYPES)
    if not saved:
        print(f"No saved pages in {inbox}/. Run `uv run sources todo --open` and save pages there.")
        return 1
    for f in saved:
        when = dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        if f.suffix.lower() == ".pdf":
            dest = out_dir / f.name
            shutil.copy2(f, dest)
            print(f"  pdf   {f.name} -> {dest} (read the PDF directly)")
            continue
        page = parse_saved(f, [p["url"] for p in wanted.values()])
        if page["challenge"]:
            problems += 1
            print(f"  SKIP  {f.name}: bot-check page, not the policy. Load the page fully, then save again.")
            continue
        if not page["url"]:
            print(f"  warn  {f.name}: source URL not found in the file; named after the file instead")
        key = norm_url(page["url"]) if page["url"] else ""
        got.add(key)
        hits = excerpts(page["text"])
        body = [
            f"Source URL: {page['url'] or '(unknown)'}",
            f"Title: {page['title']}",
            f"Saved file: {f.name} (saved {when})",
            f"Listed in blocked.yaml: {'yes - ' + wanted[key]['for'] if key in wanted else 'no'}",
            "",
            f"== AI-related passages ({len(hits)}) ==",
            *[f"- {h}" for h in hits],
            "",
            "== Full text ==",
            page["text"],
        ]
        dest = out_dir / f"{_slug(page['url'], f.stem)}.txt"
        dest.write_text("\n".join(body) + "\n", encoding="utf-8")
        print(f"  ok    {f.name} -> {dest} ({len(hits)} AI passages)")
    missing = [p for k, p in wanted.items() if k not in got]
    print(f"\n{len(wanted) - len(missing)}/{len(wanted)} blocked pages collected.")
    for p in missing:
        print(f"  still needed: {p['url']}  ({p['for']})")
    return 1 if problems else 0


def todo(open_pages: bool, inbox: Path = INBOX, blocked: Path = BLOCKED) -> int:
    inbox.mkdir(parents=True, exist_ok=True)
    listed = load_blocked(blocked)
    have = set()
    for f in inbox.glob("*.htm*"):
        page = parse_saved(f, [p["url"] for p in listed])
        if page["url"] and not page["challenge"]:
            have.add(norm_url(page["url"]))
    pages = [p for p in listed if norm_url(p["url"]) not in have]
    if not pages:
        print("All blocked pages are in the inbox. Run `uv run sources extract`.")
        return 0
    print(f"Save each page into {inbox.resolve()}/ (Cmd/Ctrl+S, format 'Webpage, HTML Only' or 'Page Source'):\n")
    for p in pages:
        print(f"  {p['url']}\n      {p['for']} - {p['why']}")
        if open_pages:
            webbrowser.open_new_tab(p["url"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sources", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("todo", help="list blocked pages not yet saved in the inbox")
    t.add_argument("--open", action="store_true", help="open each page in your default browser")
    sub.add_parser("extract", help="convert saved pages in the inbox to text")
    args = parser.parse_args(argv)
    try:
        return todo(args.open) if args.cmd == "todo" else extract()
    except FileNotFoundError as e:
        print(f"error: {e.filename} not found (run from the repository root)", file=sys.stderr)
        return 1

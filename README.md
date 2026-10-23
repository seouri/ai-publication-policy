# AI Publication Policy

**Live site:** https://seouri.github.io/ai-publication-policy/

An interactive map showing how generative-AI policies for manuscript preparation cascade through biomedical publishing. Each layer below inherits from the one above:

```
framework (ICMJE, COPE, WAME, STM, ISCB)
  → publisher (Springer Nature, Elsevier, OUP, JAMA Network, AAAS, …)
    → journal (Nature, Science, JAMIA, NEJM AI, Lancet Digital Health, …)
      → article-type rule (e.g. JAMA opinion pieces, Lancet World Report)
```

Every layer adds requirements of its own. Where two layers conflict, the stricter applicable one binds you. The page makes that lineage visible, so you can see which rule actually governs your submission.

The scope is clinical and biomedical informatics venues: about 40 frameworks, publishers, journals and article-type rules, plus a strictness matrix that also covers the major ML and informatics conferences. The date of the last survey is shown at the top of the page and set in `data/survey.yaml`.

## What's on the page

- **The common floor.** These rules hold everywhere surveyed: AI cannot be an author, humans are accountable for AI output, AI used in the research goes in Methods, undisclosed use counts as misconduct, and reviewers may not put manuscripts into public AI tools.
- **The cascade.** A tree running left to right through the four tiers.
  - Each node is colored by overall strictness, from 1 to 5.
  - Each node is marked if it is stricter than its parent (▲), looser (▼), inconsistent with it (≠), or only partly verified (⚠).
  - Click a node to highlight its lineage and open a panel showing what that layer adds, with a link to the source.
- **The strictness matrix.** Frameworks, publishers and conferences scored against five rules: how much you must disclose, whether grammar edits are exempt, AI drafting, AI images, and reviewer AI use. Hover a cell to see the policy wording behind its score.

The page is a single self-contained HTML file, with no server and no external scripts beyond Google Fonts. It supports light and dark mode, and the strictness palette passes checks for color-vision deficiency and contrast.

## Quick start

You need [uv](https://docs.astral.sh/uv/).

```sh
git clone <this repo>
cd ai-publication-policy
uv sync
uv run build-page          # writes dist/index.html
open dist/index.html
```

Other commands:

```sh
uv run build-page --check  # validate data/ without writing
uv run build-page --out site/index.html
uv run build-page --fragment   # body only, for hosts that add their own <html>/<head> (Claude artifacts)
uv run pytest
```

## Deployment

`.github/workflows/pages.yml` publishes the site to GitHub Pages on every push to `main`, and can also be run by hand from the Actions tab. It runs the tests, builds the standalone page into `_site/index.html`, and deploys it.

The workflow skips itself while the repository is private, so pushes before going public won't produce failed runs. First-time setup is one manual step. In **Settings → Pages → Build and deployment**, set **Source** to **GitHub Actions**, then push to `main` or run the workflow.

## How the data was gathered and scored

- **Sources.** Every node links to the official policy page or PDF it was taken from.
- **Fallbacks.** When a publisher's site blocked automated access, the data came from an Internet Archive snapshot, publisher PDFs, or search-engine excerpts of the official page.
- **⚠ flag.** Anything that could not be confirmed from an official source has a ⚠ and a note saying why.
- **Strictness scores.** Both the tree's 1–5 scores and the matrix's 1–4 scores are the maintainers' reading of the policy text, not an official classification. They are there for comparing policies at a glance. The rules text and the source link are what count.
- **Unscored cells.** A grey matrix cell means the policy doesn't address that rule, or that it couldn't be verified.

Known gaps as of the last check (October 2026):
- Cell Press pages are based on search excerpts only, because cell.com blocks automated access and has no archive copies.
- The Lancet reviewer rule comes from an August 2025 archive, and ACM's reviewer rules were not checked.
- The legacy LLM wording at Nature Machine Intelligence, Nature Methods, Nature Biotechnology and Nature Biomedical Engineering was last checked before October 2026.
- The AMIA 2027 Amplify call could not be read.
- The Vancouver Standard has no published text yet; recheck it in early 2027.

> **Disclaimer.** This is a research aid, not authoritative guidance. Journal policies changed repeatedly in 2025–26, so always check the venue's current author instructions before you submit.

## Repository layout

```
data/
  frameworks.yaml   Tier 1: cross-publisher frameworks and society overlays
  publishers.yaml   Tier 2 publishers, each nesting its Tier 3 journals and Tier 4 article_rules
  matrix.yaml       strictness matrix (columns + grouped rows)
  survey.yaml       date of the last survey (set by hand)
src/ai_publication_policy/
  template.html     page markup, styles and rendering script; data is injected at the /*@DATA@*/ marker
  build.py          loads and validates the YAML, renders the page
tests/              build and validation tests
.github/workflows/  GitHub Pages deployment
```

All content lives in `data/`. Adding or changing a venue never requires touching the template.

## Updating the data

### Add a journal

Append it under its publisher in `publishers.yaml`:

```yaml
- id: lancet                 # unique across all files
  name: The Lancet
  strictness: 4              # 1 (permissive) … 5 (restrictive), or null if unscored
  vs_parent: stricter        # same | stricter | looser | inconsistent | unverified
  url: https://…             # policy source
  verdict: One-line summary shown under the name.
  rules:                     # what this layer adds beyond its publisher
    - …
  note: ⚠ Optional caveat. Including ⚠ flags the node as partly unverified.
  cites: [icmje]             # optional links to Tier 1 frameworks
  article_rules:             # optional Tier 4 rules for specific article types
    - id: lancet-comment
      name: Comment
      sub: The Lancet
      strictness: 5
      url: https://…
      verdict: …
      rules: [ … ]
```

The order of entries in the file sets the top-to-bottom order in the tree.

### Add a publisher

Add an entry to `publishers:` with the same fields as a journal, except `vs_parent`. A publisher needs at least one journal, because the page positions each publisher beside its journals. Use `cites:` to link it to frameworks.

### Add a framework or society overlay

Add an entry to `frameworks.yaml`, then put its id in the `cites:` list of each publisher or journal that adopts it. To draw a faint edge for an uncertain link, use `weak_cites:`. Every id in `weak_cites:` must also appear in `cites:`.

### Optional fields

- `tier:` overrides the default label ("Publisher", "Journal", …), e.g. `Journal · flagship`.
- `date:` is the date the policy was last updated.
- `sub:` adds a second line under the name. It is used on article-type rules.

### Matrix

Add a row under the right group in `matrix.yaml`. Each column key takes `[score, text]`:
- `score` runs from 1 (permissive) to 4 (most restrictive). Use `null` when the policy doesn't address the rule or it couldn't be verified.
- A column you leave out renders as `[null, "Not stated"]`.

### Survey date

`data/survey.yaml` holds `last_surveyed`, the day the policy sources were last rechecked against official pages. It appears in the page header and footer. Change it only after actually re-verifying sources. Leave it alone for code, layout or wording changes, and don't bump it for commits or deploys. The build never takes the date from the clock.

### Footer

The source list and caveats in the footer are plain HTML in `template.html`. Edit them there.

### Validation

`build-page` fails, and names the offending entry, if it finds any of these:
- unknown fields or duplicate ids
- citations of an unknown id, or of a node in the same or a later tier
- out-of-range scores
- missing required fields (`id`, `name`, `url`, `verdict`, `rules`)

## Contributing

Corrections and additions are welcome, especially when a policy changes.

1. Open an issue or pull request that names the venue and links the **official** policy page, with the date you checked it.
2. Quote the relevant wording, so reviewers can check it without access to the page.
3. If you could only reach a secondary source, add the entry anyway with a `⚠` note saying so.
4. Run `uv run build-page --check && uv run pytest` before submitting.

## License

- **Code** (everything outside `data/`) is under the [MIT License](LICENSE).
- **Data** (`data/*.yaml`) is under [CC BY 4.0](data/LICENSE). You can reuse and adapt it with attribution, for example: "AI Publication Policy by Joon Lee, https://github.com/seouri/ai-publication-policy".

Quoted policy wording belongs to the respective publishers and is reproduced in short excerpts for comment and comparison.

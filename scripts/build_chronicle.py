#!/usr/bin/env python3
"""
Build the /chronicle/ page from markdown sources.

The Interplanetary Chronicle is a fully satirical, entirely fictional "news"
outlet. This generator is a sibling of scripts/build_updates.py and shares its
frontmatter format:

  - It writes chronicle/index.html.
  - It keeps the /chronicle/ entry in sitemap.xml in sync (lastmod = newest
    article), inserting it if missing.
  - It does NOT touch the homepage (index.html). The home page links to the
    Chronicle via a hand-written, deliberately static promo box — the
    satirical content must never be generated onto the main site.

Source of truth: content/chronicle/*.md — one file per article, each starting
with a small frontmatter block:

    ---
    date: 2026-07-17
    title: A satirical headline
    summary: One-line teaser for the in-page index. Falls back to the first
             paragraph of the body when omitted.
    ---

    The body is plain **markdown**: [links](https://example.com), lists, etc.

Layout of the generated page:
  - a masthead box (title + tagline + satire disclaimer + back-home button)
  - an index box: teaser cards (same format as the homepage update cards) that
    link down to each article's anchor on this same page
  - one box per article, newest first

Run from the repo root:  python3 scripts/build_chronicle.py
Requires the `markdown` package (same venv step as build_updates.py).

Reuses only Tailwind utility classes and the .update-body rules already present
in the committed styles.css, so no CSS rebuild is needed.
"""

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "chronicle"
CHRONICLE_PAGE = ROOT / "chronicle" / "index.html"
SITEMAP = ROOT / "sitemap.xml"

SITE = "https://amthonie.nl"

TITLE = "The Interplanetary Chronicle"
TAGLINE = "Because reality isn’t ridiculous enough."
DISCLAIMER = (
    "Everything below is entirely fictional. Any resemblance to real people, "
    "events or planets is purely unfortunate."
)

# The Chronicle's (fictional) house correspondent — used as the schema.org
# author across articles.
AUTHOR = "Amthonie Vandenberg"

# schema.org publisher description — the machine-readable "this is satire"
# signal, paired with the SatiricalArticle type on each article.
PUBLISHER_ID = f"{SITE}/chronicle/#publisher"
PUBLISHER_DESCRIPTION = (
    "A fully satirical, entirely fictional interplanetary news outlet. All "
    "names, quotes, events and reporting are invented for comic effect and are "
    "not real."
)

# Shared section-box styling, lifted verbatim from the updates page so the
# Chronicle sits in the same visual language as the rest of the site.
SECTION_FIRST = (
    "mt-3 md:mt-6 lg:mt-10 w-full md:w-4/5 max-w-[1024px] rounded-2xl "
    "border border-black/10 bg-black/5 dark:border-white/15 dark:bg-white/10 "
    "px-4 py-4 md:px-8 md:py-8 shadow-xl"
)
SECTION_NEXT = (
    "mt-2.5 md:mt-5 lg:mt-8 w-full md:w-4/5 max-w-[1024px] rounded-2xl "
    "border border-black/10 bg-black/5 dark:border-white/15 dark:bg-white/10 "
    "px-4 py-4 md:px-8 md:py-8 shadow-xl"
)

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def human_date(d: datetime) -> str:
    """Render a date the same way the gallery captions do, e.g. '16 July 2026'."""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "article"


def parse_post(path: Path) -> dict:
    """Parse one markdown file with a leading '--- ... ---' frontmatter block."""
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith("---"):
        raise SystemExit(f"{path.name}: missing frontmatter (expected a leading '---' block)")

    # Split into frontmatter and body. maxsplit=2 leaves any later '---'
    # (markdown horizontal rules) untouched inside the body.
    _, front, body = text.split("---", 2)

    meta: dict[str, str] = {}
    for line in front.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()

    for required in ("date", "title"):
        if required not in meta:
            raise SystemExit(f"{path.name}: frontmatter is missing '{required}'")

    try:
        date = datetime.strptime(meta["date"], "%Y-%m-%d")
    except ValueError:
        raise SystemExit(f"{path.name}: date '{meta['date']}' must be YYYY-MM-DD")

    body = body.strip()
    body_html = markdown.markdown(body, extensions=["extra", "sane_lists"])

    # Teaser summary: explicit frontmatter wins, else the first paragraph's text.
    summary = meta.get("summary")
    if not summary:
        first_para = re.search(r"<p>(.*?)</p>", body_html, re.DOTALL)
        summary = re.sub(r"<[^>]+>", "", first_para.group(1)).strip() if first_para else ""

    # A stable anchor: strip a leading date prefix from the filename if present.
    stem = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
    slug = slugify(stem)

    return {
        "date": date,
        "title": meta["title"],
        "summary": summary,
        "body_html": body_html,
        "slug": slug,
    }


def load_posts() -> list[dict]:
    if not CONTENT_DIR.is_dir():
        return []
    posts = [parse_post(p) for p in CONTENT_DIR.glob("*.md")]
    posts.sort(key=lambda p: p["date"], reverse=True)

    seen: set[str] = set()
    for post in posts:
        slug = post["slug"]
        n = 2
        while slug in seen:  # guarantee unique anchors
            slug = f"{post['slug']}-{n}"
            n += 1
        post["slug"] = slug
        seen.add(slug)
    return posts


def render_index(posts: list[dict]) -> str:
    """The in-page table of contents — teaser cards linking to each article.

    Same card markup as the homepage update teasers, but the href is an in-page
    anchor (#slug) rather than a link to another page.
    """
    if not posts:
        return (
            '<p class="text-sm text-stone-600 dark:text-stone-400">'
            "Nothing filed yet — the newsroom is unusually quiet.</p>"
        )

    cards = []
    for post in posts:
        summary = html.escape(post["summary"])
        cards.append(
            f"""<a href="#{post['slug']}"
               class="group flex flex-col rounded-xl border border-black/10 bg-black/5 p-2.5 md:p-5 text-left transition hover:border-black/20 hover:bg-black/10 dark:border-white/10 dark:bg-white/5 dark:hover:border-white/25 dark:hover:bg-white/10">
                <time datetime="{post['date']:%Y-%m-%d}"
                      class="text-xs font-medium uppercase tracking-wide text-brand-600 dark:text-brand-400">
                    {human_date(post['date'])}
                </time>
                <h3 class="mt-1 font-semibold text-stone-900 dark:text-white transition group-hover:text-brand-600 dark:group-hover:text-brand-400">
                    {html.escape(post['title'])}
                </h3>
                <p class="mt-1 text-sm leading-relaxed text-stone-600 dark:text-stone-300">
                    {summary}
                </p>
            </a>"""
        )
    return "\n".join(cards)


def render_article_boxes(posts: list[dict]) -> str:
    """One section box per article, newest first."""
    if not posts:
        return ""

    boxes = []
    for post in posts:
        boxes.append(
            f"""    <section id="{post['slug']}" class="{SECTION_NEXT} scroll-mt-28">
        <article>
            <time datetime="{post['date']:%Y-%m-%d}"
                  class="text-xs font-medium uppercase tracking-wide text-brand-600 dark:text-brand-400">
                {human_date(post['date'])}
            </time>
            <h2 class="mt-1 text-2xl md:text-3xl font-bold tracking-tight text-stone-900 dark:text-white">
                {html.escape(post['title'])}
            </h2>
            <div class="update-body mt-4">
                {post['body_html']}
            </div>
        </article>
    </section>"""
        )
    return "\n".join(boxes)


def build_jsonld(posts: list[dict]) -> str:
    """schema.org structured data.

    Emits a NewsMediaOrganization publisher plus one SatiricalArticle per post.
    `SatiricalArticle` is schema.org's canonical signal that a piece is satire
    rather than genuine reporting — the strongest machine-readable "this is not
    real" marker for search engines.
    """
    publisher = {
        "@type": "NewsMediaOrganization",
        "@id": PUBLISHER_ID,
        "name": TITLE,
        "url": f"{SITE}/chronicle/",
        "slogan": TAGLINE,
        "description": PUBLISHER_DESCRIPTION,
        "logo": {
            "@type": "ImageObject",
            "url": f"{SITE}/images/a.png",
        },
    }

    graph: list[dict] = [publisher]
    for post in posts:
        url = f"{SITE}/chronicle/#{post['slug']}"
        graph.append(
            {
                "@type": "SatiricalArticle",
                "@id": url,
                "mainEntityOfPage": url,
                "headline": post["title"],
                "description": post["summary"],
                "datePublished": f"{post['date']:%Y-%m-%d}",
                "inLanguage": "en-GB",
                "isFamilyFriendly": True,
                "abstract": "Satire — a work of fiction. Nothing described here is real.",
                "author": {"@type": "Person", "name": AUTHOR},
                "publisher": {"@id": PUBLISHER_ID},
            }
        )

    data = {"@context": "https://schema.org", "@graph": graph}
    # ensure_ascii=False keeps curly quotes/emoji readable; escaping '<' keeps
    # the payload safe to embed inside a <script> element.
    payload = json.dumps(data, indent=2, ensure_ascii=False).replace("<", "\\u003c")
    return f'<script type="application/ld+json">\n{payload}\n    </script>'


def build_chronicle_page(posts: list[dict]) -> None:
    index_cards = render_index(posts)
    article_boxes = render_article_boxes(posts)
    jsonld = build_jsonld(posts)
    page = f"""<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>{TITLE} | {TAGLINE}</title>
    <link rel="canonical" href="{SITE}/chronicle/">
    <link rel="icon" href="../favicon.ico" sizes="any"/>
    <link rel="icon" type="image/png" href="../images/a.png"/>
    <meta name="description"
          content="A fully satirical and entirely fictional interplanetary news outlet — dry corporate humour, fabricated reporting, and absurd takes on the elite. None of this is real."/>
    <meta name="theme-color" content="#C77B5E" media="(prefers-color-scheme: light)"/>
    <meta name="theme-color" content="#222222" media="(prefers-color-scheme: dark)"/>
    <meta name="robots" content="index,follow,noarchive"/>

    <meta property="og:type" content="article"/>
    <meta property="og:url" content="{SITE}/chronicle/"/>
    <meta property="og:title" content="{TITLE}"/>
    <meta property="og:description"
          content="A fully satirical, entirely fictional interplanetary news outlet. Nothing here is real."/>
    <meta property="og:site_name" content="{TITLE}"/>
    <meta property="og:locale" content="en_GB"/>

    <!-- schema.org structured data: NewsMediaOrganization publisher +
         SatiricalArticle per post (the canonical "this is satire" signal). -->
    {jsonld}

    <!-- Precompiled Tailwind (built from src/input.css by the Pages workflow) -->
    <link rel="stylesheet" href="../styles.css"/>
</head>

<body class="flex flex-col min-h-screen bg-paper text-stone-800 antialiased dark:bg-black dark:text-stone-200">
<main class="flex min-h-screen flex-col items-center px-2.5 md:px-6 pt-6 md:pt-12 pb-12 md:pb-24">

    <!-- Header banner — links back to the home page -->
    <a
            href="../"
            aria-label="Back to home"
            class="group relative block w-full md:w-4/5 max-w-[1024px] aspect-[4/1] overflow-hidden rounded-2xl shadow-lg ring-1 ring-black/5 transition hover:ring-brand-500/60 dark:ring-white/10 dark:hover:ring-brand-400/60">
        <img
                src="header.webp"
                alt="Decorative abstract header background for The Interplanetary Chronicle"
                aria-hidden="true"
                class="absolute inset-0 h-full w-full object-cover object-top transition duration-500 group-hover:scale-105"
                draggable="false"
        />
    </a>

    <!-- Masthead -->
    <section class="{SECTION_FIRST}">
        <div class="flex items-start justify-between gap-4">
            <div>
                <h1 class="text-2xl md:text-3xl font-bold tracking-tight text-stone-900 dark:text-white">{TITLE}</h1>
                <p class="mt-1 text-sm font-medium uppercase tracking-wide text-brand-600 dark:text-brand-400">{TAGLINE}</p>
            </div>
            <a href="../"
               class="shrink-0 inline-flex items-center gap-1.5 rounded-full border border-black/10 bg-black/5 px-4 py-2 text-sm font-medium text-stone-700 transition hover:bg-black/10 dark:border-white/15 dark:bg-white/10 dark:text-stone-200 dark:hover:bg-white/20">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M19 12H5"/>
                    <path d="m12 19-7-7 7-7"/>
                </svg>
                Back home
            </a>
        </div>
        <p class="mt-4 text-sm italic leading-relaxed text-stone-600 dark:text-stone-400">{DISCLAIMER}</p>
    </section>

    <!-- Index -->
    <section class="{SECTION_NEXT}">
        <h2 class="text-2xl font-bold tracking-tight text-stone-900 dark:text-white">In this edition</h2>
        <div class="mt-3 md:mt-6 grid gap-2 md:gap-4 sm:grid-cols-2">
            {index_cards}
        </div>
    </section>

    <!-- Articles -->
{article_boxes}
</main>

<!-- Footer -->
<footer class="w-full mt-auto py-4 text-center text-xs text-stone-500 dark:text-stone-400">
    <p>A work of satire — entirely fictional.</p>
    <p class="mt-1">&copy; <span id="year"></span> Amthonie</p>
</footer>

<script>
    document.getElementById('year').textContent = new Date().getFullYear();
</script>
</body>
</html>
"""
    CHRONICLE_PAGE.parent.mkdir(parents=True, exist_ok=True)
    CHRONICLE_PAGE.write_text(page, encoding="utf-8")
    print(f"wrote {CHRONICLE_PAGE.relative_to(ROOT)} ({len(posts)} article(s))")


def _set_lastmod(text: str, loc: str, lastmod: str) -> str:
    """Update the <lastmod> of an existing <loc> in place (no-op if absent)."""
    return re.sub(
        rf"(<loc>{re.escape(loc)}</loc>\s*<lastmod>)[^<]*(</lastmod>)",
        rf"\g<1>{lastmod}\g<2>",
        text,
    )


def update_sitemap(posts: list[dict]) -> None:
    """Keep the /chronicle/ sitemap entry in sync with the newest article.

    Only touches the /chronicle/ <loc> — inserts it if missing, otherwise bumps
    its lastmod. The home page is left alone on purpose: its Chronicle promo box
    is static, so new articles don't change it.
    """
    if not posts:
        return
    lastmod = f"{posts[0]['date']:%Y-%m-%d}"
    chronicle_loc = f"{SITE}/chronicle/"
    text = SITEMAP.read_text(encoding="utf-8")

    if chronicle_loc in text:
        text = _set_lastmod(text, chronicle_loc, lastmod)
    else:
        entry = (
            "    <url>\n"
            f"        <loc>{chronicle_loc}</loc>\n"
            f"        <lastmod>{lastmod}</lastmod>\n"
            "    </url>\n"
        )
        text = text.replace("</urlset>", entry + "</urlset>")

    SITEMAP.write_text(text, encoding="utf-8")
    print(f"sitemap.xml: /chronicle/ lastmod {lastmod}")


def main() -> int:
    posts = load_posts()
    build_chronicle_page(posts)
    update_sitemap(posts)
    return 0


if __name__ == "__main__":
    sys.exit(main())

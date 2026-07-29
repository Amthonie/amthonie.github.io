#!/usr/bin/env python3
"""
Build the /jottings/ page (and the homepage teasers) from markdown sources.

Source of truth: content/jottings/*.md — one file per jotting, each starting
with a small frontmatter block:

    ---
    date: 2026-07-16
    slug: 99-a-short-headline
    title: A short headline
    summary: Optional one-line teaser for the homepage. Falls back to the first
             paragraph of the body when omitted.
    ---

    Only `date` and `title` are required. `slug` is optional — it sets the page
    #anchor (and the homepage teaser link); omit it and one is derived from the
    filename. `summary` is optional too.

    The body is plain **markdown**: [links](https://example.com), lists, etc.

Outputs (all committed as build artifacts, exactly like styles.css):
  - jottings/index.html  full list, newest first, served at /jottings/
  - index.html           teaser cards injected between the
                         <!-- JOTTINGS:START --> / <!-- JOTTINGS:END --> markers
  - sitemap.xml          /jottings/ entry kept in sync (lastmod = newest post)

Run from the repo root:  python3 scripts/build_jottings.py
Requires the `markdown` package (see the venv step in the Pages workflow).

Deliberately dependency-light and self-contained: raw markdown lives under
content/ (excluded from the published site), and the generated HTML uses only
static CSS (the .update-body rules in src/input.css) plus the same Tailwind
utility classes already used elsewhere — so no typography plugin is needed and
the committed styles.css stays valid.
"""

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "jottings"
JOTTINGS_PAGE = ROOT / "jottings" / "index.html"
INDEX_PAGE = ROOT / "index.html"
SITEMAP = ROOT / "sitemap.xml"

SITE = "https://amthonie.nl"
# Full intro — used for the visible page intro and the (uncapped) JSON-LD.
DESCRIPTION = (
    "A small collection of passing thoughts, brief notes, and the occasional "
    "observation that seemed worth writing down — nothing grand, just the quiet "
    "debris of daily life that lingered long enough to be captured."
)
# Shorter form for the <meta name="description"> and og:description, kept near
# the ~155-char length search engines display before truncating.
META_DESCRIPTION = (
    "A small collection of passing thoughts, brief notes, and the occasional "
    "observation that seemed worth writing down."
)
TEASERS_ON_HOME = 4  # how many of the newest jottings to show on the homepage
                     # (fills the 2-column grid in index.html as two rows of two)

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def human_date(d: datetime) -> str:
    """Render a date the same way the gallery captions do, e.g. '16 July 2026'."""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "jotting"


def open_external_links_in_new_tab(html: str) -> str:
    """Make off-site links in rendered markdown open in a new tab.

    Body links that point off-site (an ``http(s)://`` URL) get
    ``target="_blank" rel="noopener"``, mirroring the curated links on the home
    page. Relative links and in-page ``#anchors`` are left untouched, so
    same-site navigation stays in the current tab.
    """
    def add_target(match: re.Match) -> str:
        attrs = match.group(1)
        href = re.search(r'href="([^"]*)"', attrs)
        if not href or not href.group(1).startswith(("http://", "https://")):
            return match.group(0)
        if "target=" in attrs:  # respect an explicit target if one is ever set
            return match.group(0)
        return f'<a {attrs} target="_blank" rel="noopener">'

    return re.sub(r"<a ([^>]*?)>", add_target, html)


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
    body_html = open_external_links_in_new_tab(
        markdown.markdown(body, extensions=["extra", "sane_lists"])
    )

    # Teaser summary: explicit frontmatter wins, else the first paragraph's text.
    summary = meta.get("summary")
    if not summary:
        first_para = re.search(r"<p>(.*?)</p>", body_html, re.DOTALL)
        summary = re.sub(r"<[^>]+>", "", first_para.group(1)).strip() if first_para else ""

    # A stable anchor: an explicit frontmatter `slug` wins; otherwise fall back
    # to the filename with any leading number prefix stripped (files are named
    # like 0009-a-short-headline.md). Either way it is run through slugify() so
    # the result is always URL/anchor-safe.
    slug = meta.get("slug") or re.sub(r"^\d+-", "", path.stem)
    slug = slugify(slug)

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


SECTION_CLASS = (
    "mt-3 md:mt-6 lg:mt-10 w-full md:w-4/5 max-w-[1280px] rounded-2xl border "
    "border-black/5 bg-black/5 dark:border-white/10 dark:bg-white/10 px-4 py-4 "
    "md:px-8 md:py-8 shadow-xl"
)


def render_articles(posts: list[dict]) -> str:
    """Render the jottings as one top-level box per month, newest month first.

    Each month's entries share a box, separated by the usual <hr> divider;
    the months themselves come out as separate boxes (August above July, …).
    Posts arrive already sorted newest-first, so both orders fall out for free.
    """
    if not posts:
        return (
            f'<section class="{SECTION_CLASS}">'
            '<p class="text-stone-600 dark:text-stone-400">No jottings yet — '
            "check back soon.</p></section>"
        )

    # Group consecutive posts by (year, month), preserving the newest-first order.
    groups: list[tuple[int, int, list[dict]]] = []
    for post in posts:
        year, month = post["date"].year, post["date"].month
        if not groups or groups[-1][0] != year or groups[-1][1] != month:
            groups.append((year, month, []))
        groups[-1][2].append(post)

    sections = []
    for _year, _month, items in groups:
        blocks = []
        for i, post in enumerate(items):
            divider = "" if i == 0 else (
                '<hr class="my-10 border-black/10 dark:border-white/10"/>'
            )
            blocks.append(
                f"""{divider}
            <article id="{post['slug']}" class="scroll-mt-28">
                <time datetime="{post['date']:%Y-%m-%d}"
                      class="text-xs font-medium uppercase tracking-wide text-brand-600 dark:text-brand-400">
                    {human_date(post['date'])}
                </time>
                <h2 class="mt-1 text-2xl font-bold tracking-tight text-stone-900 dark:text-white">
                    {html.escape(post['title'])}
                </h2>
                <div class="update-body mt-4">
                    {post['body_html']}
                </div>
            </article>"""
            )
        sections.append(
            f'<section class="{SECTION_CLASS}">\n{"".join(blocks)}\n    </section>'
        )
    return "\n".join(sections)


def render_index(posts: list[dict]) -> str:
    """A compact in-page table of contents, grouped by month, newest first.

    Only worth showing once there's more than one jotting. Each month gets its
    own first-level card; inside it the titles run as a single dotted line
    (Title • Title • …) rather than a bullet list, so the whole archive stays
    compact and scannable as it grows. The month label is itself an anchor link
    to its card, giving each month a permalink. Posts arrive already sorted
    newest-first, so the months come out newest-first too.
    """
    if len(posts) < 2:
        return ""

    # Group consecutive posts by (year, month), preserving the newest-first order.
    groups: list[tuple[int, int, list[dict]]] = []
    for post in posts:
        year, month = post["date"].year, post["date"].month
        if not groups or groups[-1][0] != year or groups[-1][1] != month:
            groups.append((year, month, []))
        groups[-1][2].append(post)

    # Literal spaces around the dot (not a Tailwind mx-* utility): the fractional
    # margin classes aren't in the committed styles.css, so a class-based gap
    # renders as zero on the preview and on mobile.
    # A bold brand-coloured dot at the text's own size, so it stays aligned with
    # the titles and never makes a wrapped line taller than a dot-free one.
    separator = (
        ' <span aria-hidden="true" '
        'class="font-bold text-brand-600 dark:text-brand-400">&bull;</span> '
    )

    blocks = []
    for year, month, items in groups:
        anchor = f"m-{year}-{month:02d}"
        label = f"{MONTHS[month - 1]} {year}"
        links = separator.join(
            f'<a href="#{post["slug"]}" '
            f'class="text-stone-800 dark:text-stone-100 transition '
            f'hover:text-brand-600 dark:hover:text-brand-400">'
            f'{html.escape(post["title"])}</a>'
            for post in items
        )
        # A thin rule above every month — including the first, so it also
        # separates the intro text from the index. Plain blocks inside the one
        # first-level box, rather than a box per month, to avoid the boxy
        # nested-card look.
        divider = '<hr class="my-4 border-black/10 dark:border-white/10"/>'
        blocks.append(
            f"""{divider}
        <div id="{anchor}" class="scroll-mt-28">
            <a href="#{anchor}"
               class="text-base font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">
                {label}
            </a>
            <p class="mt-2 text-sm leading-relaxed">
                {links}
            </p>
        </div>"""
        )

    return f"""<nav aria-label="All jottings" class="mt-5 md:mt-8">
        {"".join(blocks)}
    </nav>"""


def render_teasers(posts: list[dict]) -> str:
    if not posts:
        return (
            '<p class="text-sm text-stone-600 dark:text-stone-400">'
            "Nothing here yet — jottings will appear as I post them.</p>"
        )

    cards = []
    for post in posts[:TEASERS_ON_HOME]:
        summary = html.escape(post["summary"])
        cards.append(
            f"""<a href="jottings/#{post['slug']}"
               class="group flex flex-col rounded-xl border border-black/5 bg-black/5 shadow-md p-2.5 md:p-5 text-left transition hover:border-black/10 hover:bg-black/10 dark:border-white/10 dark:bg-white/10 dark:hover:border-white/20 dark:hover:bg-white/20">
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


def build_jsonld() -> str:
    """schema.org CollectionPage for the jottings listing.

    Built with json.dumps (not inlined into the page f-string) so the JSON
    braces don't collide with f-string substitution — the same approach used by
    build_chronicle.py. Cross-links to the homepage graph via @id references.
    """
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": f"{SITE}/jottings/#webpage",
                "primaryImageOfPage": {
                    "@type": "ImageObject",
                    "url": f"{SITE}/images/theme/nouveau/og-image.jpg",
                    "width": 1200,
                    "height": 630,
                },
                "url": f"{SITE}/jottings/",
                "name": "Jottings",
                "description": DESCRIPTION,
                "isPartOf": {"@id": f"{SITE}/#website"},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                    {"@type": "ListItem", "position": 2, "name": "Jottings", "item": f"{SITE}/jottings/"},
                ],
            },
        ],
    }
    payload = json.dumps(data, indent=4, ensure_ascii=False).replace("<", "\\u003c")
    # Indent the JSON under the <script> tag (8 spaces) so the block aligns with
    # the hand-authored JSON-LD on the other pages.
    payload = "\n".join(f"        {line}" for line in payload.splitlines())
    return f'<script type="application/ld+json">\n{payload}\n    </script>'


def build_jottings_page(posts: list[dict]) -> None:
    articles = render_articles(posts)
    index = render_index(posts)
    jsonld = build_jsonld()
    page = f"""<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Amthonie | Jottings</title>
    <link rel="canonical" href="{SITE}/jottings/">
    <link rel="icon" href="../favicon.ico" sizes="any"/>
    <link rel="icon" type="image/png" href="../images/a.png"/>
    <meta name="description"
          content="{META_DESCRIPTION}"/>
    <meta name="theme-color" content="#4A7A2C" media="(prefers-color-scheme: light)"/>
    <meta name="theme-color" content="#3A5F22" media="(prefers-color-scheme: dark)"/>
    <meta name="robots" content="index,follow"/>

    <meta property="og:type" content="website"/>
    <meta property="og:url" content="{SITE}/jottings/"/>
    <meta property="og:title" content="Amthonie | Jottings"/>
    <meta property="og:description"
          content="{META_DESCRIPTION}"/>
    <meta property="og:image" content="{SITE}/images/theme/nouveau/og-image.jpg"/>
    <meta property="og:site_name" content="Amthonie"/>
    <meta property="og:locale" content="en_GB"/>

    {jsonld}

    <!-- Precompiled Tailwind (built from src/input.css by the Pages workflow) -->
    <link rel="stylesheet" href="../styles.css"/>

    <!-- Google tag (gtag.js) -->
    <script defer src="https://www.googletagmanager.com/gtag/js?id=G-EX67104T6F"></script>
    <script>
        window.dataLayer = window.dataLayer || [];

        function gtag() {{
            dataLayer.push(arguments);
        }}

        window.addEventListener('DOMContentLoaded', function () {{
            gtag('js', new Date());
            gtag('config', 'G-EX67104T6F');
        }});
    </script>
</head>

<body class="flex flex-col min-h-screen bg-paper text-stone-800 antialiased dark:bg-stone-900 dark:text-stone-100">
<main class="flex min-h-screen flex-col items-center px-2.5 md:px-6 pt-6 md:pt-12 pb-12 md:pb-24">

    <!-- Header: banner image + branded band merged into one box (matches the home page).
         The Amthonie wordmark sits in the band with a back-home button; no subtitle or socials. -->
    <div class="w-full md:w-4/5 max-w-[1280px] overflow-hidden rounded-2xl shadow-xl ring-1 ring-black/5 dark:ring-white/10">
        <a href="../" aria-label="Back to home" class="group relative block aspect-[4/1] overflow-hidden">
            <img
                    src="../images/theme/nouveau/header.webp"
                    alt="Decorative abstract header background"
                    aria-hidden="true"
                    class="absolute inset-0 h-full w-full object-cover object-top transition duration-500 group-hover:scale-105"
                    draggable="false"
            />
            <img
                    src="../images/theme/nouveau/avatar.webp"
                    alt="Profile picture of Amthonie"
                    class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 aspect-square h-[150%] rounded-full object-cover bg-stone-800 ring-2 ring-stone-800 shadow-md"
                    draggable="false"
            />
        </a>
        <div class="flex items-center justify-between gap-6 bg-brand-600 dark:bg-brand-700 px-4 py-4 md:px-8 md:py-6">
            <p class="text-2xl md:text-3xl font-bold tracking-tight text-white">Amthonie</p>
            <a href="../"
               aria-label="Back to home"
               class="shrink-0 inline-flex items-center gap-1.5 rounded-full border border-white/25 bg-white/15 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/25">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                     stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M19 12H5"/>
                    <path d="m12 19-7-7 7-7"/>
                </svg>
                Back home
            </a>
        </div>
    </div>

    <!-- Jottings: intro + index -->
    <section
            class="mt-3 md:mt-6 lg:mt-10 w-full md:w-4/5 max-w-[1280px] rounded-2xl border border-black/5 bg-black/5 dark:border-white/10 dark:bg-white/10 px-4 py-4 md:px-8 md:py-8 shadow-xl">

        <h1 class="text-2xl font-bold tracking-tight text-stone-900 dark:text-white">Jottings</h1>

        <p class="mt-3 text-base font-semibold leading-relaxed text-stone-600 dark:text-stone-400">{DESCRIPTION}</p>

        {index}
    </section>

    <!-- Jottings: the entries themselves, one box per month -->
    {articles}
</main>

<!-- Footer -->
<footer class="w-full mt-auto py-4 text-center text-xs text-stone-500 dark:text-stone-400">
    <nav class="site-nav center">
        <a href="/">Home</a>
        <span class="sep">·</span>
        <a href="/about/">About me</a>
        <span class="sep">·</span>
        <a href="/naarden/">About Naarden</a>
        <span class="sep">·</span>
        <a href="/jottings/">Jottings</a>
    </nav>
    <p>&copy; <span id="year"></span> Amthonie — A light static site, minimal footprint</p>
</footer>

<script>
    document.getElementById('year').textContent = new Date().getFullYear();
</script>
</body>
</html>
"""
    JOTTINGS_PAGE.parent.mkdir(parents=True, exist_ok=True)
    JOTTINGS_PAGE.write_text(page, encoding="utf-8")
    print(f"wrote {JOTTINGS_PAGE.relative_to(ROOT)} ({len(posts)} jotting(s))")


def inject_home_teasers(posts: list[dict]) -> None:
    marker = re.compile(
        r"(<!-- JOTTINGS:START -->).*?(<!-- JOTTINGS:END -->)", re.DOTALL
    )
    text = INDEX_PAGE.read_text(encoding="utf-8")
    if not marker.search(text):
        raise SystemExit(
            "index.html is missing the <!-- JOTTINGS:START --> / "
            "<!-- JOTTINGS:END --> markers"
        )
    teasers = render_teasers(posts)
    new_text = marker.sub(rf"\1\n{teasers}\n\2", text)
    if new_text != text:
        INDEX_PAGE.write_text(new_text, encoding="utf-8")
        print("updated index.html teasers")
    else:
        print("index.html teasers unchanged")


def _set_lastmod(text: str, loc: str, lastmod: str) -> str:
    """Update the <lastmod> of an existing <loc> in place (no-op if absent)."""
    return re.sub(
        rf"(<loc>{re.escape(loc)}</loc>\s*<lastmod>)[^<]*(</lastmod>)",
        rf"\g<1>{lastmod}\g<2>",
        text,
    )


def update_sitemap(posts: list[dict]) -> None:
    """Keep the sitemap in sync with the newest jotting.

    Ensures a /jottings/ entry exists, and bumps both /jottings/ and the home
    page lastmod to the newest post's date — the home page changes because its
    teaser cards do. The gallery entry is left untouched (jottings don't affect
    it).
    """
    if not posts:
        return
    lastmod = f"{posts[0]['date']:%Y-%m-%d}"
    jottings_loc = f"{SITE}/jottings/"
    home_loc = f"{SITE}/"
    text = SITEMAP.read_text(encoding="utf-8")

    if jottings_loc in text:
        text = _set_lastmod(text, jottings_loc, lastmod)
    else:
        entry = (
            "    <url>\n"
            f"        <loc>{jottings_loc}</loc>\n"
            f"        <lastmod>{lastmod}</lastmod>\n"
            "    </url>\n"
        )
        text = text.replace("</urlset>", entry + "</urlset>")

    text = _set_lastmod(text, home_loc, lastmod)

    SITEMAP.write_text(text, encoding="utf-8")
    print(f"sitemap.xml: home + /jottings/ lastmod {lastmod}")


def main() -> int:
    posts = load_posts()
    build_jottings_page(posts)
    inject_home_teasers(posts)
    update_sitemap(posts)
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Build the /jottings/ page (and the homepage teasers) from markdown sources.

Source of truth: content/jottings/*.md — one file per jotting, each starting
with a small frontmatter block:

    ---
    id: 99
    date: 2026-07-16
    slug: a-short-headline
    title: A short headline
    summary: Optional one-line teaser for the homepage. Falls back to the first
             paragraph of the body when omitted.
    ---

    `id`, `date` and `title` are required. The page #anchor (and the homepage
    teaser link) is "<id>-<slug>", e.g. 99-a-short-headline. `slug` is optional —
    omit it and it's derived from the (required) title, slugified. `summary` is
    optional too.

    An image can be floated beside a jotting (see render_figure) via optional
    `image` / `image_alt` / `image_caption` / `image_side` fields.

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
import struct
import sys
from datetime import datetime
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "jottings"
JOTTINGS_PAGE = ROOT / "jottings" / "index.html"
JOTTINGS_IMAGES = ROOT / "jottings" / "images"  # full-size webp; thumbs in ./thumbnails/
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


def webp_size(path: Path) -> tuple[int, int] | None:
    """Return (width, height) of a WebP file by reading its RIFF header only.

    Handles the three chunk variants ImageMagick emits: simple lossy ``VP8 ``,
    simple lossless ``VP8L`` and extended ``VP8X``. Dependency-light on purpose
    (no Pillow/imagesize) — every jotting image comes from Ralph's WebP pipeline.
    Returns None when the file is missing or not a WebP we can read.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 30 or data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    fourcc = data[12:16]
    if fourcc == b"VP8 ":  # simple lossy — 14-bit dims at fixed offsets
        w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
        h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
        return w, h
    if fourcc == b"VP8L":  # simple lossless — 14-bit dims packed after the 0x2F sig
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if fourcc == b"VP8X":  # extended — 24-bit canvas dims, stored minus one
        w = (data[24] | (data[25] << 8) | (data[26] << 16)) + 1
        h = (data[27] | (data[28] << 8) | (data[29] << 16)) + 1
        return w, h
    return None


def render_figure(meta: dict, source_name: str) -> str:
    """Build a floated <figure> for a jotting from its `image:` frontmatter.

    Mirrors the figures on the Naarden page: the thumbnail is shown and links to
    the full-size image in a new tab; on desktop it floats beside the text
    (right by default, `image_side: left` to flip). The one jotting-specific
    twist is portrait handling — a portrait image is *not* shown full-width on
    mobile (that would tower over the note); it's centred at two-thirds width and
    capped, so it stays a tidy inset. Orientation is auto-detected from the
    image's own WebP header, so nothing extra need be set in frontmatter.

    Files live under jottings/images/ (full) and jottings/images/thumbnails/
    (thumb); the page is served from /jottings/, so the emitted paths are
    relative (images/… and images/thumbnails/…). A missing full-size file is a
    hard error — a typo'd filename should fail the build, not ship a broken img.
    """
    name = meta["image"]
    full_path = JOTTINGS_IMAGES / name
    thumb_path = JOTTINGS_IMAGES / "thumbnails" / name
    if not full_path.is_file():
        raise SystemExit(
            f"{source_name}: image '{name}' not found at "
            f"{full_path.relative_to(ROOT)}"
        )

    # Thumbnail is preferred for display; fall back to the full image if absent.
    thumb_rel = f"images/thumbnails/{name}" if thumb_path.is_file() else f"images/{name}"
    full_rel = f"images/{name}"

    # Orientation + intrinsic dimensions from whichever file we display (guards
    # against layout shift via width/height, and drives the portrait sizing).
    dims = webp_size(thumb_path if thumb_path.is_file() else full_path)
    is_portrait = bool(dims and dims[1] > dims[0])
    dim_attrs = f' width="{dims[0]}" height="{dims[1]}"' if dims else ""

    # PhotoSwipe opens the full-size image, so it needs *its* real pixel size on
    # the link (data-pswp-width/height, read straight from the file). Without
    # them the lightbox init skips this link and it stays a plain new-tab link —
    # a clean graceful fallback. The optional caption rides along as data-caption.
    full_dims = webp_size(full_path)
    pswp_attrs = (
        f' data-pswp-width="{full_dims[0]}" data-pswp-height="{full_dims[1]}"'
        if full_dims else ""
    )
    caption_attr = (
        f' data-caption="{html.escape(meta["image_caption"])}"'
        if meta.get("image_caption") else ""
    )

    side = meta.get("image_side", "right").lower()
    if side == "left":
        float_cls = "md:float-left md:mr-6"
    else:
        float_cls = "md:float-right md:ml-6"

    # Mobile: portrait → centred inset at half the screen width (50vw), capped;
    # landscape → full width (as Naarden). Desktop: a slim floated column either
    # way — for portrait the max-w cap governs the width (50vw is far wider than
    # the cap on a desktop viewport), for landscape an explicit fraction does.
    if is_portrait:
        size_cls = "mx-auto w-[50vw] max-w-[240px] md:my-0 md:mb-3"
    else:
        size_cls = "w-full md:my-0 md:mb-3 md:w-1/3 xl:w-1/4"
    fig_cls = f"my-4 {size_cls} {float_cls}"

    alt = html.escape(meta.get("image_alt", meta.get("title", "")))

    caption = ""
    if meta.get("image_caption"):
        caption = (
            '\n                    <figcaption class="mt-1.5 text-xs text-stone-500 '
            f'dark:text-stone-400">{html.escape(meta["image_caption"])}</figcaption>'
        )

    return f"""<figure class="{fig_cls}">
                    <a href="{full_rel}"{pswp_attrs}{caption_attr} target="_blank" rel="noopener"
                       class="group block overflow-hidden rounded-xl bg-black/10 shadow-md ring-1 ring-black/5 dark:bg-white/5 dark:ring-white/10">
                        <img src="{thumb_rel}" alt="{alt}" loading="lazy"{dim_attrs}
                             class="block w-full transition duration-300 group-hover:scale-105"/>
                    </a>{caption}
                </figure>"""


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

    for required in ("id", "date", "title"):
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

    # The published anchor is "<id>-<slug>" (e.g. 11-play-is-mandatory). The `id`
    # is the first frontmatter field (required) and namespaces the anchor; the
    # `slug` is the human-readable tail. The slug is optional — omit it and it
    # falls back to the (required) title. Either way it's run through slugify()
    # so the anchor is always URL/anchor-safe. Title, not filename, so it's
    # editable from a phone (where files can't easily be renamed).
    jotting_id = meta["id"]
    slug = meta.get("slug") or meta["title"]
    slug = slugify(slug)
    anchor = f"{jotting_id}-{slug}"

    # Optional floated image (see render_figure). Only built when `image:` is set.
    figure_html = render_figure(meta, path.name) if meta.get("image") else ""

    return {
        "date": date,
        "title": meta["title"],
        "summary": summary,
        "body_html": body_html,
        "figure_html": figure_html,
        "id": jotting_id,
        "slug": slug,
        "anchor": anchor,
    }


def load_posts() -> list[dict]:
    if not CONTENT_DIR.is_dir():
        return []
    posts = [parse_post(p) for p in CONTENT_DIR.glob("*.md")]
    # Newest first: by date, then by numeric id within a shared date — so a
    # jotting posted the same day as an earlier one still sorts above it (ids
    # only ever increase). Without the id tiebreaker the stable sort would keep
    # same-date posts in filename order, burying the newer one. See issue #92.
    posts.sort(key=lambda p: (p["date"], int(p["id"])), reverse=True)

    seen: set[str] = set()
    for post in posts:
        anchor = post["anchor"]
        n = 2
        while anchor in seen:  # guarantee unique anchors
            anchor = f"{post['anchor']}-{n}"
            n += 1
        post["anchor"] = anchor
        seen.add(anchor)
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
            # With an image, wrap the figure + body in a flow-root so the float
            # is contained inside the article (and the text top-aligns with the
            # image); without one, keep the body as the bare update-body content.
            if post["figure_html"]:
                body = (
                    f'<div class="flow-root">\n'
                    f'                    {post["figure_html"]}\n'
                    f'                    {post["body_html"]}\n'
                    f'                </div>'
                )
            else:
                body = post["body_html"]
            blocks.append(
                f"""{divider}
            <article id="{post['anchor']}" class="scroll-mt-28">
                <time datetime="{post['date']:%Y-%m-%d}"
                      class="text-xs font-medium uppercase tracking-wide text-brand-600 dark:text-brand-400">
                    {human_date(post['date'])}
                </time>
                <h2 class="mt-1 text-2xl font-bold tracking-tight text-stone-900 dark:text-white">
                    {html.escape(post['title'])}
                </h2>
                <div class="update-body mt-4">
                    {body}
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
            f'<a href="#{post["anchor"]}" '
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
            f"""<a href="jottings/#{post['anchor']}"
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


# PhotoSwipe lightbox, ported from the Naarden gallery (same self-hosted vendor
# files, same relative depth). gallery=".update-body" scopes a gallery to each
# article, so a jotting's image(s) open on their own rather than as one big
# cross-jotting gallery. The main module is imported on demand at first open, so
# page load stays light. The caption element shows data-caption, else the alt.
# Injected only when at least one jotting on the page carries an image.
PHOTOSWIPE_SCRIPT = """<!-- PhotoSwipe: a per-jotting single-image lightbox (self-hosted; see naarden). -->
<script type="module">
    import PhotoSwipeLightbox from '../vendor/photoswipe/photoswipe-lightbox.esm.min.js';

    const lightbox = new PhotoSwipeLightbox({
        gallery: '.update-body',
        children: 'a[data-pswp-width]',
        pswpModule: () => import('../vendor/photoswipe/photoswipe.esm.min.js'),
    });

    // Caption below each slide: prefer the narrative data-caption, then alt.
    lightbox.on('uiRegister', () => {
        lightbox.pswp.ui.registerElement({
            name: 'caption',
            order: 9,
            isButton: false,
            appendTo: 'root',
            html: '',
            onInit: (el, pswp) => {
                el.style.cssText =
                    'position:absolute;bottom:16px;left:0;right:0;text-align:center;' +
                    'color:#fff;font:14px/1.4 system-ui,sans-serif;padding:0 16px;' +
                    'text-shadow:0 1px 3px rgba(0,0,0,.6);pointer-events:none;';
                pswp.on('change', () => {
                    const link = pswp.currSlide.data.element;
                    const img = link?.querySelector('img');
                    el.textContent =
                        link?.getAttribute('data-caption') ||
                        (img ? img.getAttribute('alt') : '');
                });
            },
        });
    });

    lightbox.init();
</script>
"""


def build_jottings_page(posts: list[dict]) -> None:
    articles = render_articles(posts)
    index = render_index(posts)
    jsonld = build_jsonld()

    # PhotoSwipe assets only when a jotting on the page has an image (keeps an
    # image-free listing exactly as it was — no vendor CSS/JS, no behaviour).
    has_image = any(post["figure_html"] for post in posts)
    pswp_css = (
        '    <!-- PhotoSwipe stylesheet (self-hosted; only when a jotting has an image) -->\n'
        '    <link rel="stylesheet" href="../vendor/photoswipe/photoswipe.css"/>\n\n'
        if has_image else ""
    )
    pswp_script = f"\n{PHOTOSWIPE_SCRIPT}" if has_image else ""
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

{pswp_css}    <!-- Precompiled Tailwind (built from src/input.css by the Pages workflow) -->
    <link rel="stylesheet" href="../styles.css"/>

    <!-- Umami tag -->
    <script defer src="https://cloud.umami.is/script.js" data-website-id="7ea47516-43a9-4ffe-b65d-52642e7b3c28" data-domains="amthonie.nl" data-tag="jottings"></script>
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
{pswp_script}
<!-- Umami Outbound links tracking -->
<script type="text/javascript">
  (() => {{
    const name = 'outbound-link-click';
    document.querySelectorAll('a').forEach(a => {{
      if (a.host !== window.location.host && !a.getAttribute('data-umami-event')) {{
        a.setAttribute('data-umami-event', name);
        a.setAttribute('data-umami-event-url', a.href);
      }}
    }});
  }})();
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

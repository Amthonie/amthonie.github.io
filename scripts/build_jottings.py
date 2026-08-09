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

    A `tags: [a, b]` list may also be present. These are **intentionally
    collected but not consumed yet** — reserved for a future client-side
    tag-filter UI (pills) on the jottings page, deferred until the collection is
    large enough to be worth it. They are NOT dead metadata: leave them in place.
    (Full plan lives in the repo-local, gitignored CLAUDE.md.)

    The body is plain **markdown**: [links](https://example.com), lists, etc.
    Fenced code blocks work with either ``` or ''' as the fence.

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
    "debris of daily life."
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


_QUOTE_FENCE_RE = re.compile(r"^([ \t]*)'{3,}([\w#.+-]*)[ \t]*$", re.MULTILINE)


def convert_quote_fences(text: str) -> str:
    """Let jottings fence code blocks with ``'''`` as well as the standard
    markdown ```` ``` ````` (see issue #101 — three backticks is an awkward
    reach on some keyboards). Only whole fence lines — optionally followed by
    a language hint, e.g. ``'''python`` — are rewritten to backticks before
    handing the body to markdown.extensions.fenced_code; apostrophes inside
    prose (e.g. "Bach's") never occupy a whole line by themselves, so they're
    untouched. Opening and closing fences both become plain ``` so they still
    match each other regardless of how many quotes were typed.
    """
    return _QUOTE_FENCE_RE.sub(lambda m: f"{m.group(1)}```{m.group(2)}", text)


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

    body = convert_quote_fences(body.strip())
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

    # Tags: the frontmatter is parsed line-by-line (not YAML), so `tags` arrives
    # as the raw string "[hiking, wildlife]". Turn it into a real list here — the
    # jottings-page tag filter needs it as data, and everything downstream
    # (all_tags aggregation, the per-article/per-index `data-tags`) keys off it.
    tags = [
        t.strip()
        for t in meta.get("tags", "").strip().strip("[]").split(",")
        if t.strip()
    ]

    return {
        "date": date,
        "title": meta["title"],
        "summary": summary,
        "body_html": body_html,
        "figure_html": figure_html,
        "id": jotting_id,
        "slug": slug,
        "anchor": anchor,
        "tags": tags,
        # Raw image fields (not just the built figure_html) so the homepage
        # teaser can show its own small thumbnail. None when the jotting has no
        # image yet — the teaser then falls back to a text-only card.
        "image": meta.get("image"),
        "image_alt": meta.get("image_alt", meta["title"]),
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
    for year, month, items in groups:
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
            <article id="{post['anchor']}" class="scroll-mt-28" data-tags="{','.join(post['tags'])}">
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
        # The month anchor (e.g. m-2026-07) lives on the month's article box, so
        # the index's month permalink jumps here — not to the index entry itself.
        anchor = f"m-{year}-{month:02d}"
        sections.append(
            f'<section id="{anchor}" class="scroll-mt-28 {SECTION_CLASS}">\n{"".join(blocks)}\n    </section>'
        )
    return "\n".join(sections)


# Disclosure chevron for the foldable month index and the filter box. Inherits
# currentColor; rotates 90° when its <details> is open (see FEATURE_CSS).
CHEV_SVG = ('<svg class="jot-chev h-4 w-4 shrink-0" viewBox="0 0 20 20" '
            'fill="currentColor" aria-hidden="true"><path d="M7 4l7 6-7 6z"/></svg>')


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

    blocks = []
    for gi, (year, month, items) in enumerate(groups):
        anchor = f"m-{year}-{month:02d}"
        label = f"{MONTHS[month - 1]} {year}"
        # Each title is a hide-together unit (span) carrying its own (invisible)
        # data-tags, so the tag filter can drop an entry cleanly. The dotted
        # separator is drawn by CSS (.jot-idx::after) so it hides with its entry;
        # the filter script trims the trailing dot off the last visible one.
        entries = "".join(
            f'<span class="jot-idx" data-tags="{",".join(post["tags"])}">'
            f'<a href="#{post["anchor"]}" '
            f'class="text-stone-800 dark:text-stone-100 transition '
            f'hover:text-brand-600 dark:hover:text-brand-400">'
            f'{html.escape(post["title"])}</a></span>'
            for post in items
        )
        # No rules between months — the folds separate by their own spacing; the
        # only rules in this area bracket the filter box above. Each month is a
        # native <details> fold: the newest month (gi == 0) opens by default,
        # older months stay collapsed so the index stays short. (The month name
        # is a disclosure toggle now, not a jump link — the jump-to-month
        # permalink lived here before.)
        open_attr = " open" if gi == 0 else ""
        blocks.append(
            f"""
        <details class="jot-fold jot-month mt-3 first:mt-0"{open_attr}>
            <summary class="flex cursor-pointer items-center gap-2 text-base font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">
                {CHEV_SVG}{label}
            </summary>
            <p class="mt-2 text-sm leading-relaxed">
                {entries}
            </p>
        </details>"""
        )

    return f"""<nav aria-label="All jottings" class="mt-4">
        {"".join(blocks)}
    </nav>"""


def render_filter(posts: list[dict]) -> str:
    """The jottings tag-filter control.

    A collapsed-by-default <details> of tag pills with a **muted** (non-brand)
    header, so the brand-green month headings keep the visual focus. Wrapped in a
    `hidden` container that the filter script reveals — a no-JS visitor never sees
    a dead control (the pills only do anything with JS), and every jotting stays
    in the HTML regardless. Returns "" when no jotting carries a tag.
    """
    counts: dict[str, int] = {}
    for post in posts:
        for tag in post["tags"]:
            counts[tag] = counts.get(tag, 0) + 1
    if not counts:
        return ""
    tags = sorted(counts)  # alphabetical

    # Active styling is driven by the aria-pressed attribute the script toggles
    # (Tailwind's aria-pressed: variant), so JS never touches classes. The count
    # badge uses text-current/opacity so it reads on both the muted and the
    # brand-filled (active) pill without a second colour rule.
    pill = ("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm "
            "font-medium transition border-black/10 bg-black/5 text-stone-700 hover:bg-black/10 "
            "dark:border-white/15 dark:bg-white/10 dark:text-stone-200 dark:hover:bg-white/20 "
            "aria-pressed:border-brand-600 aria-pressed:bg-brand-600 aria-pressed:text-white "
            "dark:aria-pressed:border-brand-400 dark:aria-pressed:bg-brand-500 dark:aria-pressed:text-white")
    # Brand-outlined (not muted grey) so "Show all" reads as an action, not a
    # disabled pill — outline-brand for the reset vs filled-brand for a selected tag.
    reset = ("inline-flex items-center rounded-full border px-3 py-1 text-sm font-medium "
             "transition border-brand-600 bg-transparent text-brand-600 hover:bg-brand-600/10 "
             "dark:border-brand-400 dark:text-brand-400 dark:hover:bg-brand-400/10")

    buttons = [f'<button type="button" data-jot-all class="{reset}">Show all</button>']
    for tag in tags:
        buttons.append(
            f'<button type="button" data-jot-tag="{tag}" aria-pressed="false" class="{pill}">'
            f'{tag}<span class="ml-1 text-xs opacity-70">{counts[tag]}</span></button>'
        )

    # Its own box, but transparent + borderless (no card chrome, no rules) — just
    # width-aligned to the surrounding cards (same md:w-4/5 + px-4 md:px-8) so the
    # pills line up with the card content. Sits in the gutter between the title
    # card and the index card, lighter than a slab.
    return f"""<section class="jot-filter mt-2.5 md:mt-5 lg:mt-8 w-full md:w-4/5 max-w-[1280px] px-4 md:px-8" hidden>
        <details class="jot-fold">
            <summary class="inline-flex cursor-pointer items-center gap-2 text-sm font-semibold uppercase tracking-wide text-stone-600 dark:text-stone-300">
                {CHEV_SVG}Filter by tag
            </summary>
            <div class="mt-3" role="group" aria-label="Filter jottings by tag">
                <div class="flex flex-wrap gap-2">
                    {"".join(buttons)}
                </div>
                <p class="mt-3 text-xs text-stone-500 dark:text-stone-400" aria-live="polite" data-jot-count></p>
            </div>
        </details>
    </section>"""


def render_teasers(posts: list[dict]) -> str:
    if not posts:
        return (
            '<p class="text-sm text-stone-600 dark:text-stone-400">'
            "Nothing here yet — jottings will appear as I post them.</p>"
        )

    cards = []
    for position, post in enumerate(posts[:TEASERS_ON_HOME], start=1):
        summary = html.escape(post["summary"])

        # Text block (time + title + summary) — identical whether or not the
        # card carries a thumbnail.
        text_block = f"""<div class="flex min-w-0 flex-col">
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
                </div>"""

        # Optional thumbnail, ~1/3 width, filling the card height so rows stay
        # tidy. It rides inside the card's own <a>, so a click just follows the
        # link (no lightbox — unlike the article figures). Falls back to the
        # full image if the thumb is missing; text-only when there's no image.
        thumb_html = ""
        layout_cls = "flex flex-col"
        if post["image"]:
            name = post["image"]
            thumb_path = JOTTINGS_IMAGES / "thumbnails" / name
            thumb_rel = (
                f"jottings/images/thumbnails/{name}"
                if thumb_path.is_file()
                else f"jottings/images/{name}"
            )
            dims = webp_size(thumb_path if thumb_path.is_file() else JOTTINGS_IMAGES / name)
            dim_attrs = f' width="{dims[0]}" height="{dims[1]}"' if dims else ""
            alt = html.escape(post["image_alt"])
            # Full-height strip: the ~1/3-width column stretches to the card
            # height (items-stretch), and the image is absolutely positioned to
            # fill it (inset-0 + object-cover). Being out of flow, the image can
            # never drive the card height, so a portrait source is centre-cropped
            # into the strip instead of ballooning the card — and there's no
            # empty space below it, whatever the text length.
            layout_cls = "flex flex-row items-stretch gap-3 md:gap-4"
            thumb_html = f"""<div class="relative w-1/3 shrink-0 self-stretch overflow-hidden rounded-lg bg-black/10 dark:bg-white/5">
                    <img src="{thumb_rel}" alt="{alt}" loading="lazy"{dim_attrs}
                         class="absolute inset-0 h-full w-full object-cover grayscale sepia-[.4] transition duration-300 group-hover:grayscale-0 group-hover:sepia-0 group-hover:scale-105"/>
                </div>
                """

        cards.append(
            f"""<a href="jottings/#{post['anchor']}"
               data-umami-event="jotting-teaser-click"
               data-umami-event-position="{position}"
               class="group {layout_cls} rounded-xl border border-black/5 bg-black/5 shadow-md p-2.5 md:p-4 text-left transition hover:border-black/10 hover:bg-black/10 dark:border-white/10 dark:bg-white/10 dark:hover:border-white/20 dark:hover:bg-white/20">
                {thumb_html}{text_block}
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


# Feature CSS for the tag filter + foldable index. Kept in a <style> block (not
# styles.css) so it's self-contained and immune to Tailwind rebuild lag — the
# same reasoning as the Naarden weather page's scoped CSS. Injected only when
# there are tags to filter.
FEATURE_CSS = """    <style>
        /* Foldable month index + filter box (build_jottings.py). */
        .jot-fold > summary { list-style: none; }
        .jot-fold > summary::-webkit-details-marker { display: none; }
        /* Colour is the primary open/closed cue (rotation alone is hard to read
           on mobile): closed = muted grey (recedes), open = brand (the active
           section). Overrides the colour the chevron would inherit from the
           summary text. */
        .jot-fold > summary .jot-chev { transition: transform .2s ease, color .2s ease; color: var(--color-stone-500); }
        .jot-fold[open] > summary .jot-chev { transform: rotate(90deg); color: var(--color-brand-600); }
        @media (prefers-color-scheme: dark) {
          .jot-fold > summary .jot-chev { color: var(--color-stone-300); }
          .jot-fold[open] > summary .jot-chev { color: var(--color-brand-400); }
        }
        /* A closed <details> hides its content via a UA `display:none` rule, but a
           Tailwind display utility (flex/block) on that content is author CSS and
           overrides it — so re-assert the hide for the closed state here. */
        .jot-fold:not([open]) > :not(summary) { display: none; }
        /* Dotted separators between index entries, drawn on each entry so a
           filtered-out entry takes its bullet with it; the script clears the
           trailing dot off the last visible entry (.jot-idx-last). */
        .jot-idx::after { content: "\\2022"; margin: 0 .45rem; font-weight: 700; color: var(--color-brand-600); }
        .jot-idx-last::after { content: none; }
        @media (prefers-color-scheme: dark) { .jot-idx::after { color: var(--color-brand-400); } }
    </style>
"""

# Progressive enhancement: the filter box ships `hidden`; this reveals it, so a
# no-JS visitor never meets a dead control and every jotting stays in the HTML.
# OR logic across pressed pills; no pressed pill = show everything. Keeps the
# index and the article boxes in sync, opens matching months and hides emptied
# ones (index + article box), and announces the count via an aria-live region.
FILTER_SCRIPT = """<!-- Jottings tag filter (progressive enhancement — hidden until this runs). -->
<script>
(() => {
    const filter = document.querySelector('.jot-filter');
    if (!filter) return;
    filter.hidden = false;

    const articles = [...document.querySelectorAll('main article[data-tags]')];
    const sections = [...document.querySelectorAll('main section[id^="m-"]')];
    const months   = [...document.querySelectorAll('nav[aria-label="All jottings"] details.jot-month')];
    const pills    = [...filter.querySelectorAll('[data-jot-tag]')];
    const allBtn   = filter.querySelector('[data-jot-all]');
    const count    = filter.querySelector('[data-jot-count]');
    // Lives on the (always-visible) Index heading, so an active filter is still
    // signalled when the pill box is collapsed.
    const activeFlag = document.querySelector('[data-jot-active]');
    const active   = new Set();

    months.forEach(m => { m.dataset.defaultOpen = m.open; });
    const tagsOf = el => (el.getAttribute('data-tags') || '').split(',').filter(Boolean);
    const show = (el, on) => { el.style.display = on ? '' : 'none'; };

    function trimSeparators() {
        months.forEach(m => {
            let last = null;
            m.querySelectorAll('.jot-idx').forEach(e => {
                e.classList.remove('jot-idx-last');
                if (e.style.display !== 'none') last = e;
            });
            if (last) last.classList.add('jot-idx-last');
        });
    }

    // The <hr> dividers between articles are siblings, not children of the
    // articles, so a hidden article would otherwise leave its rule behind. Show
    // a divider only before a visible article that has a visible predecessor —
    // so the first visible article never gets a rule above it and hidden ones
    // take their rule with them.
    function trimArticleDividers() {
        sections.forEach(s => {
            let seen = false;
            [...s.children].forEach(node => {
                if (node.matches && node.matches('article[data-tags]')) {
                    const vis = node.style.display !== 'none';
                    const hr = node.previousElementSibling;
                    if (hr && hr.tagName === 'HR') show(hr, vis && seen);
                    if (vis) seen = true;
                }
            });
        });
    }

    function apply() {
        const on = [...active];
        const match = el => on.length === 0 || tagsOf(el).some(t => on.includes(t));

        articles.forEach(a => show(a, match(a)));
        filter.ownerDocument.querySelectorAll('.jot-idx').forEach(e => show(e, match(e)));

        // Hide an article box that has no visible article (no empty boxes).
        sections.forEach(s => {
            const any = [...s.querySelectorAll('article[data-tags]')].some(a => a.style.display !== 'none');
            show(s, any);
        });

        // Index months: while filtering, open months with a match and hide (with
        // their leading rule) the ones with none; when cleared, restore defaults.
        months.forEach(m => {
            const hr = m.previousElementSibling;
            const hasHr = hr && hr.tagName === 'HR';
            if (on.length) {
                const any = [...m.querySelectorAll('.jot-idx')].some(e => e.style.display !== 'none');
                show(m, any);
                if (hasHr) show(hr, any);
                if (any) m.open = true;
            } else {
                show(m, true);
                if (hasHr) show(hr, true);
                m.open = m.dataset.defaultOpen === 'true';
            }
        });

        if (on.length) {
            const shown = articles.filter(a => a.style.display !== 'none').length;
            count.textContent = `Showing ${shown} of ${articles.length} jottings`;
        } else {
            count.textContent = '';
        }
        if (activeFlag) activeFlag.hidden = on.length === 0;
        trimSeparators();
        trimArticleDividers();
    }

    pills.forEach(p => p.addEventListener('click', () => {
        const t = p.getAttribute('data-jot-tag');
        const now = !active.has(t);
        now ? active.add(t) : active.delete(t);
        p.setAttribute('aria-pressed', String(now));
        apply();
    }));
    if (allBtn) allBtn.addEventListener('click', () => {
        active.clear();
        pills.forEach(p => p.setAttribute('aria-pressed', 'false'));
        apply();
    });
})();
</script>
"""


def build_jottings_page(posts: list[dict]) -> None:
    articles = render_articles(posts)
    index = render_index(posts)
    filter_html = render_filter(posts)
    jsonld = build_jsonld()

    # The filter CSS/JS ride along only when there are tags to filter (otherwise
    # render_filter returns "" and the page is exactly as before).
    feature_css = f"{FEATURE_CSS}\n" if filter_html else ""
    filter_script = f"\n{FILTER_SCRIPT}" if filter_html else ""

    # The month index lives in its own card under a plain (non-brand) "Index"
    # heading — a step smaller than the h1 so it reads as a section label. Only
    # emitted when there's an index to show (render_index returns "" for <2 posts).
    index_box = (
        f"""
    <!-- Jottings: the month index -->
    <section class="mt-2.5 md:mt-5 lg:mt-8 w-full md:w-4/5 max-w-[1280px] rounded-2xl border border-black/5 bg-black/5 dark:border-white/10 dark:bg-white/10 px-4 py-4 md:px-8 md:py-8 shadow-xl">
        <h2 class="text-lg font-bold tracking-tight text-stone-900 dark:text-white">Index<span data-jot-active class="ml-2 align-middle text-sm font-normal text-brand-600 dark:text-brand-400" hidden>(filtered)</span></h2>
        {index}
    </section>"""
        if index else ""
    )

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

{feature_css}
    <!-- Umami tag -->
    <script defer src="https://cloud.umami.is/script.js" data-website-id="7ea47516-43a9-4ffe-b65d-52642e7b3c28" data-domains="amthonie.nl" data-tag="jottings"></script>
</head>

<body class="flex flex-col min-h-screen bg-paper text-stone-800 antialiased dark:bg-stone-900 dark:text-stone-100">
<a href="#main" class="skip-link">Skip to content</a>

<!-- Site banner: the branding box lives in a real <header> (banner landmark),
     outside <main> so the skip link and assistive tech can bypass it. -->
<header class="flex w-full flex-col items-center px-2.5 md:px-6 pt-6 md:pt-12">

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
</header>

<main id="main" class="flex w-full flex-col items-center px-2.5 md:px-6 pb-12 md:pb-24">

    <!-- Jottings: title + tagline -->
    <section class="mt-3 md:mt-6 lg:mt-10 w-full md:w-4/5 max-w-[1280px] rounded-2xl border border-black/5 bg-black/5 dark:border-white/10 dark:bg-white/10 px-4 py-4 md:px-8 md:py-8 shadow-xl">
        <h1 class="text-2xl font-bold tracking-tight text-stone-900 dark:text-white">Jottings</h1>
        <p class="mt-3 text-base font-semibold leading-relaxed text-stone-600 dark:text-stone-400">{DESCRIPTION}</p>
    </section>

    {filter_html}
{index_box}

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
        <a href="/about/#about-this-site">About this site</a>
        <span class="sep">·</span>
        <a href="/naarden/">About Naarden</a>
        <span class="sep">·</span>
        <a href="/naarden/weather/">Weather</a>
        <span class="sep">·</span>
        <a href="/jottings/">Jottings</a>
        <span class="sep">·</span>
        <a href="/melodies/">Melodies</a>
    </nav>
    <p>&copy; <span id="year"></span> Amthonie — A light static site, minimal footprint</p>
</footer>

<script>
    document.getElementById('year').textContent = new Date().getFullYear();
</script>
{filter_script}
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

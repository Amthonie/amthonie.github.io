#!/usr/bin/env python3
"""
Build the /chronicle/ section from markdown sources.

The Interplanetary Chronicle is a fully satirical, entirely fictional "news"
outlet. This generator is a sibling of scripts/build_jottings.py and shares its
frontmatter format, but — unlike jottings — the Chronicle is split into
**separate pages per article**:

  - chronicle/index.html          — the landing page: masthead, satire
                                     disclaimer, and an index of teaser cards,
                                     each linking to an article's own page.
  - chronicle/<slug>/index.html   — one standalone page per article: a slim
                                     text masthead + a "back to the Chronicle"
                                     button, a compact satire disclaimer, and
                                     the full story (headline as the page <h1>).

  - It keeps sitemap.xml in sync: only the /chronicle/ landing is listed. The
    landing is the single search entry point; individual article pages are
    marked noindex (still fully readable and shareable — noindex only affects
    search listing, not access or OG cards) and so are kept out of the sitemap.
    This also makes slugs disposable: renaming or deleting an article leaves no
    indexed URL to rot into a 404.

There is deliberately no RSS feed: the articles are satire, and a feed would
lift the full text into readers stripped of the masthead/disclaimer framing
that marks it as fiction. The pages are shareable (each links back to its
framed self), but the content is not syndicated bare.
  - It does NOT touch the homepage (index.html). The home page links to the
    Chronicle via a hand-written, deliberately static promo box — the
    satirical content must never be generated onto the main site.

Because each article now has its own URL, the satire signal (the visible
disclaimer *and* the SatiricalArticle JSON-LD) travels with every article page,
not just the landing — so every indexable URL reads unambiguously as fiction.

Source of truth: content/chronicle/*.md — one file per article, each starting
with a small frontmatter block:

    ---
    date: 2026-07-17
    title: A satirical headline
    summary: One-line teaser for the index. Falls back to the first paragraph
             of the body when omitted.
    image: optional-hero.webp   # bare filename in chronicle/images/; omit = no hero
    ---

    The body is plain **markdown**: [links](https://example.com), lists, etc.

Run from the repo root:  python3 scripts/build_chronicle.py
Requires the `markdown` package (same venv step as build_jottings.py).

Reuses only Tailwind utility classes and the .update-body rules already present
in the committed styles.css, so no CSS rebuild is needed.
"""

import html
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "chronicle"
CHRONICLE_DIR = ROOT / "chronicle"
LANDING_PAGE = CHRONICLE_DIR / "index.html"
SITEMAP = ROOT / "sitemap.xml"

SITE = "https://amthonie.nl"

TITLE = "The Interplanetary Chronicle"
# Short suffix for article <title> tags. Article headlines are long and
# satirical, so the full name would push the <title> well past a readable
# length; "TIC" keeps the tab/label tidy.
TITLE_SHORT = "TIC"
TAGLINE = "The worst tabloid in this galaxy and beyond"
# Visible masthead sub-line. The leading ellipsis reads as a continuation of the
# banner title above it — "The Interplanetary Chronicle …the worst tabloid in
# this galaxy and beyond" — so it feels anchored rather than floating mid-row.
# Kept lowercase; the JSON-LD slogan uses the plain proper-case TAGLINE above.
TAGLINE_DISPLAY = "…the worst tabloid in this galaxy and beyond"
# The landing <title> tag (SERP/tab). Kept short and introduces the "TIC"
# acronym that the article <title> tags use as their suffix. The playful
# TAGLINE isn't lost — it stays as the visible masthead sub-line and in
# og:description — so it's dropped from <title> here to keep it tab-length.
META_TITLE = "The Interplanetary Chronicle (TIC)"
# <meta name="description"> for the landing — aim for ~120-155 chars.
META_DESCRIPTION = (
    "A satirical, entirely fictional interplanetary outlet delivering dry "
    "humour, fabricated reporting and absurd commentary. Nothing here is real."
)
DISCLAIMER = (
    "The Interplanetary Chronicle is a fully satirical and entirely fictional "
    "outlet. Any resemblance to real people, events or planets is purely "
    "unfortunate."
)

# A slim banner shown atop every article page — smaller than the landing banner
# (chronicle/header.webp) so it doesn't push the story down, but enough to give
# each standalone article the Chronicle's masthead identity. Lives in
# chronicle/; article pages are one level deeper, so they reference it as
# ../header-articles.webp. If the file is absent the article page falls back to
# a plain text wordmark.
ARTICLE_HEADER = "header-articles.webp"

# The Chronicle's (fictional) house correspondent — used as the schema.org
# author across articles.
AUTHOR = "Amthonie Vandenberg"

# schema.org publisher description — the machine-readable "this is satire"
# signal, paired with the SatiricalArticle type on each article.
PUBLISHER_ID = f"{SITE}/chronicle/#publisher"
PUBLISHER_DESCRIPTION = (
    "A fully satirical, entirely fictional interplanetary outlet. All "
    "names, quotes, events and reporting are invented for comic effect and are "
    "not real."
)

# Shared section-box styling, lifted verbatim from the jottings page so the
# Chronicle sits in the same visual language as the rest of the site.
SECTION_BOX = (
    "mt-2.5 md:mt-5 lg:mt-8 w-full md:w-4/5 max-w-[1280px] rounded-2xl "
    "border border-black/10 bg-black/5 dark:border-white/15 dark:bg-white/10 "
    "px-4 py-4 md:px-8 md:py-8 shadow-xl"
)

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def lightbox_css(prefix: str) -> str:
    return (
        '\n    <!-- PhotoSwipe styles for the click-to-zoom article hero -->'
        f'\n    <link rel="stylesheet" href="{prefix}vendor/photoswipe/photoswipe.css"/>'
    )


def lightbox_js(prefix: str) -> str:
    """PhotoSwipe init for an article page's hero image.

    Reuses the shared self-hosted copy at <prefix>vendor/ (used by both the
    Naarden gallery and these article heroes), so no third-party CDN and nothing
    to duplicate. `prefix` is the relative path back to the site root (../../ for
    an article page).
    """
    return f"""
<!-- PhotoSwipe: click the article hero to open the full image in a lightbox. -->
<script type="module">
    import PhotoSwipeLightbox from '{prefix}vendor/photoswipe/photoswipe-lightbox.esm.min.js';

    const lightbox = new PhotoSwipeLightbox({{
        gallery: 'main',
        children: 'a.pswp-hero',
        // The main module loads on demand the first time an image is opened.
        pswpModule: () => import('{prefix}vendor/photoswipe/photoswipe.esm.min.js'),
    }});

    // Caption = the hero image's alt text (the article headline).
    lightbox.on('uiRegister', () => {{
        lightbox.pswp.ui.registerElement({{
            name: 'caption',
            order: 9,
            isButton: false,
            appendTo: 'root',
            html: '',
            onInit: (el, pswp) => {{
                el.style.cssText =
                    'position:absolute;bottom:16px;left:0;right:0;text-align:center;' +
                    'color:#fff;font:14px/1.4 system-ui,sans-serif;padding:0 16px;' +
                    'text-shadow:0 1px 3px rgba(0,0,0,.6);pointer-events:none;';
                pswp.on('change', () => {{
                    const img = pswp.currSlide.data.element?.querySelector('img');
                    el.textContent = img ? img.getAttribute('alt') : '';
                }});
            }},
        }});
    }});

    lightbox.init();
</script>"""


def human_date(d: datetime) -> str:
    """Render a date the same way the gallery captions do, e.g. '16 July 2026'."""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "article"


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
    """Return a WebP's (width, height) by parsing its header — no dependencies.

    PhotoSwipe needs the image's true pixel size (data-pswp-width/height) or it
    mis-sizes the slide, so read it from the file rather than assuming. Handles
    the three WebP chunk types (lossy VP8, lossless VP8L, extended VP8X);
    returns None if the file isn't a WebP we can read.
    """
    data = path.read_bytes()[:30]
    if len(data) < 30 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return None
    fmt = data[12:16]
    if fmt == b"VP8 ":  # lossy: 14-bit width/height little-endian at offset 26
        w = int.from_bytes(data[26:28], "little") & 0x3FFF
        h = int.from_bytes(data[28:30], "little") & 0x3FFF
        return w, h
    if fmt == b"VP8L":  # lossless: 14-bit (w-1),(h-1) packed after the 0x2F sig
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if fmt == b"VP8X":  # extended: 24-bit (w-1),(h-1) at offset 24
        return (int.from_bytes(data[24:27], "little") + 1,
                int.from_bytes(data[27:30], "little") + 1)
    return None


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

    # A stable anchor/slug: an explicit frontmatter `slug` wins; otherwise fall
    # back to the filename with any leading date prefix stripped. Either way it
    # is run through slugify() so the result is always URL-safe.
    slug = meta.get("slug") or re.sub(r"^\d{4}-\d{2}-\d{2}-", "", path.stem)
    slug = slugify(slug)

    # Optional per-article hero image, declared in the frontmatter as a bare
    # filename (no path): `image: greenland-compromise.webp`. It resolves to
    # chronicle/images/<filename> and is shown uncropped alongside the story.
    # No field → no hero. A named-but-missing file is skipped with a warning
    # rather than breaking the build. `image` is stored relative to chronicle/
    # (e.g. "images/foo.webp"); article pages live one level deeper, so they
    # reference it as "../images/foo.webp".
    image = None
    image_w = image_h = None
    image_name = meta.get("image")
    if image_name:
        image_rel = f"images/{image_name}"
        image_path = CHRONICLE_DIR / image_rel
        if image_path.is_file():
            image = image_rel
            dims = webp_size(image_path)
            if dims:
                image_w, image_h = dims
            else:
                print(
                    f"warning: {path.name}: could not read dimensions of "
                    f"'{image_name}' — hero shown but not click-to-zoom",
                    file=sys.stderr,
                )
        else:
            print(
                f"warning: {path.name}: image '{image_name}' not found in "
                "chronicle/images/ — skipping hero",
                file=sys.stderr,
            )

    return {
        "date": date,
        "title": meta["title"],
        "summary": summary,
        "body_html": body_html,
        "slug": slug,
        "image": image,
        "image_w": image_w,
        "image_h": image_h,
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
        while slug in seen:  # guarantee unique per-article directories
            slug = f"{post['slug']}-{n}"
            n += 1
        post["slug"] = slug
        post["url"] = f"{SITE}/chronicle/{slug}/"
        seen.add(slug)
    return posts


# --------------------------------------------------------------------------- #
# Shared page shell
# --------------------------------------------------------------------------- #

def render_page(
    *,
    prefix: str,
    title_tag: str,
    canonical: str,
    description: str,
    og_type: str,
    og_title: str,
    og_description: str,
    og_image: str,
    jsonld: str,
    body: str,
    robots: str = "index,follow",
    has_lightbox: bool = False,
) -> str:
    """Assemble a full HTML page from the shared shell.

    `prefix` is the relative path from this page back to the site root
    ('../' for the landing, '../../' for an article page). All root-level assets
    (styles, favicon, Naarden gallery vendor, the home link) are addressed through it.
    """
    css_extra = lightbox_css(prefix) if has_lightbox else ""
    js_extra = lightbox_js(prefix) if has_lightbox else ""

    return f"""<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>{title_tag}</title>
    <link rel="canonical" href="{canonical}">
    <link rel="icon" href="{prefix}chronicle/favicon.ico" sizes="any"/>
    <link rel="icon" type="image/png" href="{prefix}chronicle/icon.png"/>
    <link rel="apple-touch-icon" href="{prefix}chronicle/icon.png"/>
    <meta name="description"
          content="{html.escape(description, quote=True)}"/>
    <meta name="theme-color" content="#1F6699" media="(prefers-color-scheme: light)"/>
    <meta name="theme-color" content="#1C1917" media="(prefers-color-scheme: dark)"/>
    <meta name="robots" content="{robots}"/>

    <meta property="og:type" content="{og_type}"/>
    <meta property="og:url" content="{canonical}"/>
    <meta property="og:title" content="{html.escape(og_title, quote=True)}"/>
    <meta property="og:description"
          content="{html.escape(og_description, quote=True)}"/>
    <meta property="og:image" content="{og_image}"/>
    <meta property="og:image:alt" content="{html.escape(og_title, quote=True)}"/>
    <meta property="og:site_name" content="{TITLE}"/>
    <meta property="og:locale" content="en_GB"/>

    <!-- schema.org structured data: NewsMediaOrganization publisher +
         SatiricalArticle (the canonical "this is satire" signal). -->
    {jsonld}

    <!-- Precompiled Tailwind (built from src/input.css by the Pages workflow) -->
    <link rel="stylesheet" href="{prefix}styles.css"/>{css_extra}

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

{body}
</main>

<!-- Footer: the satire disclaimer lives here as a quiet about-note, on every
     page (this is the shared shell). -->
<footer class="w-full mt-auto py-6 text-center text-xs text-stone-500 dark:text-stone-400">
    <p class="mx-auto max-w-xl px-4 leading-relaxed font-semibold">{DISCLAIMER}</p>
    <p class="mt-2">&copy; <span id="year"></span> Amthonie</p>
</footer>

<script>
    document.getElementById('year').textContent = new Date().getFullYear();
</script>{js_extra}
</body>
</html>
"""


# --------------------------------------------------------------------------- #
# Landing page
# --------------------------------------------------------------------------- #

def render_index_cards(posts: list[dict]) -> str:
    """The article index — teaser cards, each linking to its own article page.

    When an article has a hero image the card leads with a small thumbnail so
    the index reads like a front page. The heroes are all 3:2, so a 3:2 slot
    shows the whole poster uncropped. A 480px thumbnail in images/thumbs/ is
    preferred when present; otherwise the full hero is used. Articles without an
    image fall back to a text-only card.
    """
    if not posts:
        return (
            '<p class="text-sm text-stone-600 dark:text-stone-400">'
            "Nothing filed yet — the newsroom is unusually quiet.</p>"
        )

    cards = []
    for post in posts:
        card_img = ""
        if post["image"]:
            name = post["image"].split("/")[-1]
            thumb = f"images/thumbs/{name}"
            src = thumb if (CHRONICLE_DIR / thumb).is_file() else post["image"]
            card_img = (
                f'<img src="{src}" alt="{html.escape(post["title"])}"\n'
                '                     width="480" height="320" loading="lazy" decoding="async" draggable="false"\n'
                '                     class="aspect-[3/2] w-full object-cover transition duration-500 group-hover:scale-105"/>'
            )
        cards.append(
            f"""<a href="{post['slug']}/"
               class="group flex flex-col overflow-hidden rounded-xl border border-black/10 bg-black/5 text-left transition hover:border-black/20 hover:bg-black/10 dark:border-white/10 dark:bg-white/5 dark:hover:border-white/25 dark:hover:bg-white/10">
                {card_img}
                <div class="p-2.5 md:p-5">
                    <time datetime="{post['date']:%Y-%m-%d}"
                          class="text-xs font-medium uppercase tracking-wide text-brand-600 dark:text-brand-400">
                        {human_date(post['date'])}
                    </time>
                    <h3 class="mt-1 font-semibold uppercase leading-tight tracking-tight text-stone-900 dark:text-white transition group-hover:text-brand-600 dark:group-hover:text-brand-400">
                        {html.escape(post['title'])}
                    </h3>
                    <p class="mt-1 text-sm leading-relaxed text-stone-600 dark:text-stone-300">
                        {html.escape(post['summary'])}
                    </p>
                </div>
            </a>"""
        )
    return "\n".join(cards)


def build_landing_jsonld(posts: list[dict]) -> str:
    """Landing structured data: the publisher, a breadcrumb, and an ItemList of
    the articles (each SatiricalArticle's full markup lives on its own page)."""
    publisher = {
        "@type": "NewsMediaOrganization",
        "@id": PUBLISHER_ID,
        "name": TITLE,
        "alternateName": TITLE_SHORT,
        "url": f"{SITE}/chronicle/",
        "slogan": TAGLINE,
        "description": PUBLISHER_DESCRIPTION,
        "logo": {"@type": "ImageObject", "url": f"{SITE}/chronicle/icon.png"},
        "image": {
            "@type": "ImageObject",
            "url": f"{SITE}/chronicle/header_small.webp",
            "width": 640,
            "height": 331,
        },
    }
    collection_page = {
        "@type": "CollectionPage",
        "@id": f"{SITE}/chronicle/#webpage",
        "primaryImageOfPage": {
            "@type": "ImageObject",
            "url": f"{SITE}/chronicle/header_small.webp",
            "width": 640,
            "height": 331,
        },
        "url": f"{SITE}/chronicle/",
        "name": TITLE,
        "description": PUBLISHER_DESCRIPTION,
        "isPartOf": {"@id": f"{SITE}/#website"},
    }
    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": TITLE, "item": f"{SITE}/chronicle/"},
        ],
    }
    item_list = {
        "@type": "ItemList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "url": post["url"], "name": post["title"]}
            for i, post in enumerate(posts, start=1)
        ],
    }
    data = {"@context": "https://schema.org", "@graph": [collection_page, publisher, breadcrumb, item_list]}
    return _jsonld_script(data)


def build_landing_page(posts: list[dict]) -> None:
    index_cards = render_index_cards(posts)
    jsonld = build_landing_jsonld(posts)

    body = f"""    <!-- Header banner (decorative, non-linking): the only route back to
         amthonie.nl is the button in the sub-masthead below. -->
    <div class="relative block w-full md:w-4/5 max-w-[1280px] aspect-[2/1] overflow-hidden rounded-2xl shadow-lg ring-1 ring-black/5 dark:ring-white/10">
        <img
                src="header.webp"
                alt="Decorative abstract header background for The Interplanetary Chronicle"
                aria-hidden="true"
                class="absolute inset-0 h-full w-full object-cover object-top"
                draggable="false"
        />
    </div>

    <!-- Real site title as the page's <h1>, kept sr-only: the banner image above
         carries it visually (and it lives in <title>, og:title and the JSON-LD),
         so this gives crawlers and screen readers a genuine text <h1> without
         painting a duplicate on screen. -->
    <h1 class="sr-only">{TITLE}</h1>

    <!-- Sub-masthead (boxless): the tagline (an <h2>) and the back button sit
         directly under the image, no box, flush with the outer edges of the
         boxes below. -->
    <div class="mt-3 md:mt-6 lg:mt-10 flex w-full md:w-4/5 max-w-[1280px] items-center justify-between gap-4">
        <h2 class="text-xl font-medium italic text-stone-900 dark:text-white">{TAGLINE_DISPLAY}</h2>
        <a href="../"
           class="shrink-0 inline-flex items-center gap-1.5 rounded-full border border-black/10 bg-black/5 px-4 py-2 text-sm font-medium text-stone-700 transition hover:bg-black/10 dark:border-white/15 dark:bg-white/10 dark:text-stone-200 dark:hover:bg-white/20">
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
                <polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
            amthonie.nl
        </a>
    </div>

    <!-- Index -->
    <section class="{SECTION_BOX}">
        <h2 class="text-2xl font-bold tracking-tight text-stone-900 dark:text-white">In this edition</h2>
        <div class="mt-3 md:mt-6 grid gap-2 md:gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {index_cards}
        </div>
    </section>"""

    page = render_page(
        prefix="../",
        title_tag=META_TITLE,
        canonical=f"{SITE}/chronicle/",
        description=META_DESCRIPTION,
        og_type="website",
        og_title=TITLE,
        og_description=(
            "A fully satirical, entirely fictional interplanetary outlet. "
            "Nothing here is real."
        ),
        og_image=f"{SITE}/chronicle/header.webp",
        jsonld=jsonld,
        body=body,
        has_lightbox=False,
    )
    LANDING_PAGE.parent.mkdir(parents=True, exist_ok=True)
    LANDING_PAGE.write_text(page, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Article pages
# --------------------------------------------------------------------------- #

def render_article_hero(post: dict) -> str:
    """The optional hero illustration for an article page.

    On mobile it is a full-bleed block above the story; on wide screens (md+) it
    floats to the right at half width so the article text flows around it,
    magazine-style. No object-cover: these are vintage-poster illustrations whose
    headline sits at the very top, so any crop would clip it. When dimensions are
    known it's wrapped in a PhotoSwipe anchor (class "pswp-hero") so a click opens
    the full image in the lightbox. Article pages live in chronicle/<slug>/, so
    the image (stored relative to chronicle/) is addressed one level up.
    """
    if not post["image"]:
        return ""
    src = f"../{post['image']}"
    box = ("mt-4 block w-full md:float-right md:mt-1 md:mb-3 "
           "md:ml-6 md:w-1/2 md:max-w-md")
    w, h = post["image_w"] or 1024, post["image_h"] or 683
    if post["image_w"]:  # dimensions known → clickable lightbox hero
        return (
            f'\n            <a href="{src}"\n'
            f'               data-pswp-width="{w}" data-pswp-height="{h}"\n'
            '               target="_blank" rel="noopener"\n'
            f'               class="pswp-hero group cursor-zoom-in transition hover:opacity-95 {box}">\n'
            f'                <img src="{src}"\n'
            f'                     alt="{html.escape(post["title"])}"\n'
            '                     class="block w-full rounded-xl shadow-md ring-1 ring-black/5 dark:ring-white/10"\n'
            f'                     width="{w}" height="{h}" loading="lazy" decoding="async" draggable="false"/>\n'
            '            </a>'
        )
    return (  # unreadable dimensions → plain, non-clickable hero
        f'\n            <img src="{src}"\n'
        f'                 alt="{html.escape(post["title"])}"\n'
        f'                 class="rounded-xl shadow-md ring-1 ring-black/5 dark:ring-white/10 {box}"\n'
        f'                 width="{w}" height="{h}" loading="lazy" decoding="async" draggable="false"/>'
    )


def render_article_banner() -> str:
    """The slim masthead banner atop an article page, or '' if the file is
    missing. Links back to the Chronicle index and uses the image's true aspect
    ratio so it renders as the short, wide strip it is."""
    path = CHRONICLE_DIR / ARTICLE_HEADER
    if not path.is_file():
        return ""
    dims = webp_size(path)
    aspect = f"{dims[0]}/{dims[1]}" if dims else "1024/217"
    return f"""    <!-- Article masthead banner — links back to the Chronicle index -->
    <a
            href="../"
            aria-label="Back to The Interplanetary Chronicle"
            class="group relative block w-full md:w-4/5 max-w-[1280px] aspect-[{aspect}] overflow-hidden rounded-2xl shadow-lg ring-1 ring-black/5 transition hover:ring-brand-500/60 dark:ring-white/10 dark:hover:ring-brand-400/60">
        <img
                src="../{ARTICLE_HEADER}"
                alt="{html.escape(TITLE)}"
                class="absolute inset-0 h-full w-full object-cover object-top transition duration-500 group-hover:scale-105"
                draggable="false"
        />
    </a>
"""


def build_article_jsonld(post: dict) -> str:
    """Per-article structured data: publisher + breadcrumb + SatiricalArticle.

    `SatiricalArticle` is schema.org's canonical signal that a piece is satire
    rather than genuine reporting — the strongest machine-readable "this is not
    real" marker for search engines.
    """
    publisher = {
        "@type": "NewsMediaOrganization",
        "@id": PUBLISHER_ID,
        "name": TITLE,
        "alternateName": TITLE_SHORT,
        "url": f"{SITE}/chronicle/",
        "slogan": TAGLINE,
        "description": PUBLISHER_DESCRIPTION,
        "logo": {"@type": "ImageObject", "url": f"{SITE}/chronicle/icon.png"},
    }
    breadcrumb = {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
            {"@type": "ListItem", "position": 2, "name": TITLE, "item": f"{SITE}/chronicle/"},
            {"@type": "ListItem", "position": 3, "name": post["title"], "item": post["url"]},
        ],
    }
    article = {
        "@type": "SatiricalArticle",
        "@id": post["url"],
        "mainEntityOfPage": post["url"],
        "headline": post["title"],
        "description": post["summary"],
        "datePublished": f"{post['date']:%Y-%m-%d}",
        "inLanguage": "en-GB",
        "isFamilyFriendly": True,
        "abstract": "Satire — a work of fiction. Nothing described here is real.",
        "author": {"@type": "Person", "name": AUTHOR},
        "publisher": {"@id": PUBLISHER_ID},
    }
    if post["image"]:
        article["image"] = f"{SITE}/chronicle/{post['image']}"

    data = {"@context": "https://schema.org", "@graph": [publisher, breadcrumb, article]}
    return _jsonld_script(data)


def build_article_page(post: dict) -> None:
    hero = render_article_hero(post)
    banner = render_article_banner()

    if banner:
        # The banner carries the title, so the sub-line mirrors the landing:
        # the tagline on the left, the back button on the right. A top margin
        # separates the row from the banner above it.
        submast_left = (
            '<p class="text-xl md:text-2xl font-medium italic '
            f'text-stone-900 dark:text-white">{TAGLINE_DISPLAY}</p>'
        )
        row_class = "mt-3 md:mt-6 lg:mt-10 flex"
    else:
        # No banner file — fall back to a text wordmark as the identity, and let
        # the row sit flush at the top of <main> (no extra margin).
        submast_left = (
            '<a href="../" class="text-sm md:text-base font-semibold uppercase '
            "tracking-wide text-stone-900 transition hover:text-brand-600 "
            f'dark:text-white dark:hover:text-brand-400">{TITLE}</a>'
        )
        row_class = "flex"

    body = f"""{banner}    <!-- Sub-masthead: identity on the left, back-to-index button on the right;
         the article headline below is the page's <h1>. -->
    <div class="{row_class} w-full md:w-4/5 max-w-[1280px] items-center justify-between gap-4">
        {submast_left}
        <a href="../"
           class="shrink-0 inline-flex items-center gap-1.5 rounded-full border border-black/10 bg-black/5 px-4 py-2 text-sm font-medium text-stone-700 transition hover:bg-black/10 dark:border-white/15 dark:bg-white/10 dark:text-stone-200 dark:hover:bg-white/20">
            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                 stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <path d="m12 19-7-7 7-7"/><path d="M19 12H5"/>
            </svg>
            Front page
        </a>
    </div>

    <!-- Article -->
    <section class="{SECTION_BOX}">
        <article>
            <time datetime="{post['date']:%Y-%m-%d}"
                  class="text-xs font-medium uppercase tracking-wide text-brand-600 dark:text-brand-400">
                {human_date(post['date'])}
            </time>
            <h1 class="mt-1 text-2xl md:text-3xl font-bold tracking-tight text-stone-900 dark:text-white">
                {html.escape(post['title'])}
            </h1>{hero}
            <div class="update-body mt-4">
                {post['body_html']}
            </div>
        </article>
    </section>"""

    og_image = (
        f"{SITE}/chronicle/{post['image']}" if post["image"]
        else f"{SITE}/chronicle/header.webp"
    )
    page = render_page(
        prefix="../../",
        title_tag=f"{post['title']} | {TITLE_SHORT}",
        canonical=post["url"],
        description=post["summary"],
        og_type="article",
        og_title=post["title"],
        og_description=post["summary"],
        og_image=og_image,
        jsonld=build_article_jsonld(post),
        body=body,
        # The Chronicle landing is the single search entry point; individual
        # articles are deliberately kept out of search indexes (still fully
        # readable and shareable — noindex only affects search listing, not
        # access or OG cards). This also makes slugs disposable: renaming or
        # deleting an article leaves no indexed URL to rot into a 404.
        robots="noindex,follow",
        has_lightbox=bool(post["image_w"]),
    )
    article_dir = CHRONICLE_DIR / post["slug"]
    article_dir.mkdir(parents=True, exist_ok=True)
    (article_dir / "index.html").write_text(page, encoding="utf-8")


def clean_stale_article_dirs(slugs: set[str]) -> None:
    """Remove generated article directories whose source .md is gone.

    Only touches subdirectories of chronicle/ that look generated (contain an
    index.html) and aren't in the current slug set. `images/` and the header
    image files are left alone (images/ has no index.html).
    """
    if not CHRONICLE_DIR.is_dir():
        return
    for child in CHRONICLE_DIR.iterdir():
        if (
            child.is_dir()
            and child.name not in slugs
            and (child / "index.html").is_file()
        ):
            shutil.rmtree(child)
            print(f"removed stale article dir chronicle/{child.name}/")


# --------------------------------------------------------------------------- #
# JSON-LD helper
# --------------------------------------------------------------------------- #

def _jsonld_script(data: dict) -> str:
    # ensure_ascii=False keeps curly quotes/emoji readable; escaping '<' keeps
    # the payload safe to embed inside a <script> element.
    payload = json.dumps(data, indent=4, ensure_ascii=False).replace("<", "\\u003c")
    # Indent the JSON under the <script> tag (8 spaces) so the block aligns with
    # the hand-authored JSON-LD on the other pages.
    payload = "\n".join(f"        {line}" for line in payload.splitlines())
    return f'<script type="application/ld+json">\n{payload}\n    </script>'


# --------------------------------------------------------------------------- #
# Sitemap
# --------------------------------------------------------------------------- #

def update_sitemap(posts: list[dict]) -> None:
    """Keep the /chronicle/ sitemap entry in sync.

    Only the landing is listed (lastmod = newest article): it is the single
    search entry point. The individual article pages are deliberately kept out
    of the sitemap because they are noindex — a sitemap must never list a
    noindex URL. Entries for the rest of the site are left untouched, and the
    home page is left alone on purpose (its Chronicle promo box is static).
    """
    if not posts:
        return
    text = SITEMAP.read_text(encoding="utf-8")

    # Drop any existing chronicle blocks (landing or older per-article entries)
    # so re-runs don't duplicate and previously-listed articles don't linger.
    text = re.sub(
        r"[ \t]*<url>\s*<loc>" + re.escape(f"{SITE}/chronicle")
        + r"[^<]*</loc>.*?</url>\n?",
        "",
        text,
        flags=re.DOTALL,
    )

    entry = (
        "    <url>\n"
        f"        <loc>{SITE}/chronicle/</loc>\n"
        f"        <lastmod>{posts[0]['date']:%Y-%m-%d}</lastmod>\n"
        "    </url>\n"
    )
    text = text.replace("</urlset>", entry + "</urlset>")
    SITEMAP.write_text(text, encoding="utf-8")
    print("sitemap.xml: /chronicle/ landing only (articles are noindex)")


def main() -> int:
    posts = load_posts()
    clean_stale_article_dirs({post["slug"] for post in posts})
    build_landing_page(posts)
    for post in posts:
        build_article_page(post)
    update_sitemap(posts)
    print(f"wrote chronicle/ landing + {len(posts)} article page(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

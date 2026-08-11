#!/usr/bin/env python3
"""
Build the /melodies/ page from markdown sources.

RTTTL (Ring Tone Text Transfer Language) snippets I use as chimes/alerts on my
ESPHome devices — branded on-site as "RTTTL Melodies" / "Melodies" (the
content dir, this script's filename, and internal class names all stay
`rtttl*` since that's the underlying format; only the public-facing URL,
title, and copy use the friendlier "Melodies" name).

Source of truth: content/rtttl/*.md — one file per tune, each starting with a
small frontmatter block:

    ---
    name: Bach, Inventio 8
    rtttl: inventio_8:d=16,o=5,b=160:f,p,a,p,f,p,c6,p,a,p,f6,p,e6,d6,c6,d6,c6,a#,a,a#,a,g,8f,p;
    ---

    A brief excerpt from *Bach's Invention No. 8*, rendered in RTTTL and
    played on the hour.

    Both `name` and `rtttl` are required. The body is a short markdown
    description shown under the code block; omit it for no caption. Entries
    are ordered alphabetically by `name` (there's no natural chronology for a
    reference list like this one, unlike jottings/chronicle).

Outputs (committed as a build artefact, exactly like styles.css):
  - melodies/index.html — the page, served at /melodies/
  - sitemap.xml          — /melodies/ entry kept in sync (lastmod = build
                            date; there's no per-tune date to derive it from)

Run from the repo root:  python3 scripts/build_melodies.py
Requires the `markdown` package (see the venv step in the Pages workflow).

The page also carries two static, hand-authored sections that aren't sourced
from content/rtttl/*.md — a "Try it yourself" playbox and a "The format"
syntax primer — since they're page furniture, not per-tune data. The RTTTL
player itself is vendor/rtttl-play/ (self-hosted, MIT — see its LICENSE),
exposing window.rtttlPlay.play(str)/.stop().
"""

import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = ROOT / "content" / "rtttl"
MELODIES_PAGE = ROOT / "melodies" / "index.html"
SITEMAP = ROOT / "sitemap.xml"

SITE = "https://amthonie.nl"
# Full intro — two paragraphs rendered as the visible tagline; joined with a
# space for the (uncapped) JSON-LD description, which takes a single string.
DESCRIPTION_P1 = (
    "Ring Tone Text Transfer Language — a compact plain‑text format from the "
    "feature‑phone era, once responsible for those impressive, popular, and "
    "occasionally rather annoying ringtones — is used here to drive a "
    "piezo‑buzzer emulator in your browser. Below is a small collection of "
    "my own miniatures, ranging from Bach to early arcade themes. You can "
    "try your own in the playbox, and a short syntax guide follows for "
    "anyone curious about how these strings work."
)
DESCRIPTION_P2 = (
    "I use the format to give my reTerminal’s e‑paper display — running "
    "ESPHome — something more interesting to do than emit a single, dutiful "
    "beep. These little fragments make it play brief, occasionally "
    "irritating tunes as hourly chimes or when events occur, such as the "
    "front door opening."
)
DESCRIPTION = f"{DESCRIPTION_P1} {DESCRIPTION_P2}"
# Shorter form for <meta name="description"> / og:description.
META_DESCRIPTION = (
    "RTTTL ringtone snippets I use on my ESPHome buzzer, with an in-browser player."
)


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "tune"


def open_external_links_in_new_tab(html_text: str) -> str:
    """Make off-site links in rendered markdown open in a new tab.

    Mirrors the same helper in build_jottings.py/build_chronicle.py — each
    generator keeps its own copy on purpose (self-contained, no shared module).
    """
    def add_target(match: re.Match) -> str:
        attrs = match.group(1)
        href = re.search(r'href="([^"]*)"', attrs)
        if not href or not href.group(1).startswith(("http://", "https://")):
            return match.group(0)
        if "target=" in attrs:
            return match.group(0)
        return f'<a {attrs} target="_blank" rel="noopener">'

    return re.sub(r"<a ([^>]*?)>", add_target, html_text)


def parse_post(path: Path) -> dict:
    """Parse one markdown file with a leading '--- ... ---' frontmatter block."""
    text = path.read_text(encoding="utf-8")
    if not text.lstrip().startswith("---"):
        raise SystemExit(f"{path.name}: missing frontmatter (expected a leading '---' block)")

    _, front, body = text.split("---", 2)

    meta: dict[str, str] = {}
    for line in front.strip().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip()

    for required in ("name", "rtttl"):
        if required not in meta:
            raise SystemExit(f"{path.name}: frontmatter is missing '{required}'")

    body_html = open_external_links_in_new_tab(
        markdown.markdown(body.strip(), extensions=["extra", "sane_lists"])
    )

    return {
        "name": meta["name"],
        "rtttl": meta["rtttl"],
        "body_html": body_html,
        "slug": slugify(meta["name"]),
    }


def load_posts() -> list[dict]:
    if not CONTENT_DIR.is_dir():
        return []
    # Alphabetical by name (not filename) — there's no date field to sort by
    # (see the module docstring), and `name` is what's actually shown.
    posts = [parse_post(p) for p in CONTENT_DIR.glob("*.md")]
    posts.sort(key=lambda p: p["name"].lower())

    seen: set[str] = set()
    for post in posts:
        slug = post["slug"]
        n = 2
        while slug in seen:  # guarantee unique ids
            slug = f"{post['slug']}-{n}"
            n += 1
        post["slug"] = slug
        seen.add(slug)
    return posts


def render_item(post: dict) -> str:
    name_esc = html.escape(post["name"])
    rtttl_esc = html.escape(post["rtttl"])
    # Style each paragraph the description renders to (usually just one) —
    # deliberately a bare <p>, not .update-body, since .update-body's own
    # (unlayered, higher-precedence) color rule would otherwise beat these
    # Tailwind text-color utilities. .update-body is still used below for the
    # code block, where that's exactly the styling we want (see input.css).
    desc_html = post["body_html"].replace(
        "<p>", '<p class="mt-3 text-sm leading-relaxed text-stone-600 dark:text-stone-300">'
    )
    return f"""<div id="{post['slug']}" class="rtttl-item scroll-mt-28 w-full md:w-4/5 max-w-[1280px] panel px-4 py-4 md:px-8 md:py-8">
            <div class="flex items-center justify-between gap-4">
                <h3 class="text-lg font-bold text-stone-900 dark:text-white">{name_esc}</h3>
                <div class="flex items-center gap-2 shrink-0">
                    <button type="button" class="rtttl-play inline-flex h-9 w-9 items-center justify-center rounded-full bg-brand-600 text-white transition hover:bg-brand-700 dark:bg-brand-500 dark:hover:bg-brand-400"
                            data-rtttl="{rtttl_esc}"
                            aria-label="Play {name_esc}">
                        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
                    </button>
                    <button type="button" class="rtttl-stop inline-flex h-9 w-9 items-center justify-center rounded-full border border-black/10 bg-black/5 text-stone-700 transition hover:bg-black/10 dark:border-white/15 dark:bg-white/10 dark:text-stone-200 dark:hover:bg-white/20"
                            aria-label="Stop playback">
                        <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12"/></svg>
                    </button>
                </div>
            </div>
            <div class="update-body mt-3">
                <pre><code>{rtttl_esc}</code></pre>
            </div>
            {desc_html}
        </div>"""


# Standard content panel (see .panel in input.css): flush, square, 1px border,
# no shadow. Padding/width stay as utilities.
SECTION_CLASS = "w-full md:w-4/5 max-w-[1280px] panel px-4 py-4 md:px-8 md:py-8"


def title_panel(text: str, anchor: str) -> str:
    """A brand (green) section-title panel — the melodies equivalent of the
    jottings month headers. The section's anchor id lives here so the in-page
    nav jumps to the header; the content panel follows it, flush."""
    return (f'<div id="{anchor}" class="scroll-mt-28 w-full md:w-4/5 max-w-[1280px] '
            f'panel panel--brand px-4 py-2 md:px-8 md:py-3">'
            f'<h2 class="text-2xl font-bold tracking-tight text-white">{text}</h2></div>')


def render_items(posts: list[dict]) -> str:
    """The tune collection: a brand title panel, then each tune as its own
    `.panel` (like the jottings jotting panels) — flush-stacked, no wrapper box."""
    header = title_panel("My collection", "collection")
    if not posts:
        return (f'{header}\n'
                f'    <section class="{SECTION_CLASS}"><p class="text-stone-600 '
                'dark:text-stone-400">No tunes yet — check back soon.</p></section>')
    tunes = "\n    ".join(render_item(post) for post in posts)
    return f"{header}\n    {tunes}"


# "Try it yourself" and "The format" are page furniture, not sourced from
# content/rtttl/*.md — kept as static blocks here rather than generated.
TRY_IT_YOURSELF = f"""{title_panel("Try it yourself", "try-it")}
    <!-- RTTTL: try your own -- reads live from the textarea rather than a
         fixed data-rtttl attribute, so it gets its own listener below. -->
    <section class="{SECTION_CLASS}">
        <p class="text-sm leading-relaxed text-stone-600 dark:text-stone-300">Paste or write your own RTTTL string below and give it a play. A brief disclaimer: experimenting with this may prove unexpectedly addictive and could test the patience of nearby housemates.</p>
        <label for="rtttl-input" class="sr-only">Your RTTTL string</label>
        <textarea id="rtttl-input" rows="6" spellcheck="false"
                  placeholder="name:d=4,o=5,b=125:notes"
                  class="mt-3 w-full border border-black/10 bg-white/60 p-3 font-mono text-sm text-stone-800 shadow-inner focus:border-brand-600 focus:outline-none focus:ring-2 focus:ring-brand-600/30 dark:border-white/15 dark:bg-stone-900/40 dark:text-stone-100 dark:focus:border-brand-400 dark:focus:ring-brand-400/30"></textarea>
        <div class="mt-3 flex items-center gap-2">
            <button type="button" id="rtttl-input-play"
                    class="inline-flex items-center gap-1.5 rounded-full bg-brand-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-700 dark:bg-brand-500 dark:hover:bg-brand-400">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z"/></svg>
                Play
            </button>
            <button type="button" class="rtttl-stop inline-flex items-center gap-1.5 rounded-full border border-black/10 bg-black/5 px-4 py-2 text-sm font-medium text-stone-700 transition hover:bg-black/10 dark:border-white/15 dark:bg-white/10 dark:text-stone-200 dark:hover:bg-white/20">
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="6" width="12" height="12"/></svg>
                Stop
            </button>
        </div>
        <!-- Opt-in "remember my tinkering" switch. The only cookies on the whole
             site, and only if you turn this on: a boolean preference flag plus
             the melody text, first-party, ~1 week, no tracking. The toggle's
             visual lives in melodies.css and its wiring in melodies.js. -->
        <label class="rtttl-remember">
            <input type="checkbox" id="rtttl-remember"/>
            <span class="rtttl-remember-track" aria-hidden="true"></span>
            <span class="text-sm leading-relaxed text-stone-600 dark:text-stone-300">
                <span class="font-medium text-stone-800 dark:text-stone-200">Remember my tinkering on this device</span>
                <span class="mt-0.5 block text-xs text-stone-500 dark:text-stone-400">Saves just the melody text above — and this switch’s state — in simple, anonymous first‑party cookies for about a week, so it’s still here when you come back. Nothing else, no tracking; switch it off to delete them.</span>
            </span>
        </label>
    </section>"""

FORMAT_EXPLAINER = f"""{title_panel("The syntax", "syntax")}
    <!-- RTTTL: a basic explanation of the syntax. -->
    <section class="{SECTION_CLASS}">
        <div class="update-body">
            <p>An RTTTL string packs a whole melody into one line of plain text: a name, a few default settings, then the notes themselves.</p>
            <pre><code>name:d=4,o=5,b=125:notes
      │   │    │
      │   │    └─ tempo (BPM)
      │   └────── default octave
      └────────── default note length (4 = quarter)

note = [length]letter[#][octave][.]
  1/4/8/16/32    → length
  c d e f g a b  → notes
  p              → rest (instead of a note)
  #              → sharp (flat not supported)
  7              → octave
  .              → dotted ×1.5
  length/octave omitted → uses the d / o defaults

Examples:  8g#6 = eighth G# octave 6
           4c   = quarter C (default octave)
           8c6. = dotted eighth C6
           16p  = short rest</code></pre>
            <p>For a detailed explanation of the format as implemented in ESPHome, see the <a href="https://esphome.io/components/rtttl.html" target="_blank" rel="noopener">RTTTL component documentation</a>.</p>
        </div>
    </section>"""


# In-page section nav, shown under the header as a sub-header. A muted panel
# (grey) reusing the footer's .site-nav layout (links + "·" separators); on the
# dark fill the links read light and turn brand-400 on hover, via
# `.site-nav.panel--muted` in input.css. Anchors match the section title panels:
# #collection / #try-it / #syntax.
PAGE_NAV = """<!-- RTTTL: in-page section nav, a muted sub-header panel (light links,
         brand-400 on hover; see .site-nav.panel--muted in input.css). -->
    <nav aria-label="On this page" class="site-nav w-full md:w-4/5 max-w-[1280px] panel panel--muted px-4 py-4 md:px-8 md:py-6">
        <a href="#collection">My collection</a>
        <span class="sep">·</span>
        <a href="#try-it">Try it yourself</a>
        <span class="sep">·</span>
        <a href="#syntax">The syntax</a>
    </nav>"""


def build_jsonld() -> str:
    """schema.org CollectionPage for the RTTTL Melodies listing.

    "name" is the full page identity (matches <title>/<h1>); the breadcrumb's
    name is the short "Melodies" form, matching the footer nav label (Home >
    Melodies, same level as Jottings).
    """
    data = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "CollectionPage",
                "@id": f"{SITE}/melodies/#webpage",
                "primaryImageOfPage": {
                    "@type": "ImageObject",
                    "url": f"{SITE}/images/theme/nouveau/og-image.jpg",
                    "width": 1200,
                    "height": 630,
                },
                "url": f"{SITE}/melodies/",
                "name": "RTTTL Melodies",
                "description": DESCRIPTION,
                "isPartOf": {"@id": f"{SITE}/#website"},
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Home", "item": f"{SITE}/"},
                    {"@type": "ListItem", "position": 2, "name": "Melodies", "item": f"{SITE}/melodies/"},
                ],
            },
        ],
    }
    payload = json.dumps(data, indent=4, ensure_ascii=False).replace("<", "\\u003c")
    payload = "\n".join(f"        {line}" for line in payload.splitlines())
    return f'<script type="application/ld+json">\n{payload}\n    </script>'


def build_melodies_page(posts: list[dict]) -> None:
    jsonld = build_jsonld()
    items = render_items(posts)
    page = f"""<!DOCTYPE html>
<html lang="en" class="scroll-smooth">
<head>
    <meta charset="UTF-8"/>
    <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
    <title>Amthonie | RTTTL Melodies</title>
    <link rel="canonical" href="{SITE}/melodies/">
    <link rel="icon" href="../favicon.ico" sizes="any"/>
    <link rel="icon" type="image/png" href="../images/a.png"/>
    <meta name="description"
          content="{META_DESCRIPTION}"/>
    <meta name="theme-color" content="#4A7A2C" media="(prefers-color-scheme: light)"/>
    <meta name="theme-color" content="#3A5F22" media="(prefers-color-scheme: dark)"/>
    <meta name="robots" content="index,follow"/>

    <meta property="og:type" content="website"/>
    <meta property="og:url" content="{SITE}/melodies/"/>
    <meta property="og:title" content="Amthonie | RTTTL Melodies"/>
    <meta property="og:description"
          content="{META_DESCRIPTION}"/>
    <meta property="og:image" content="{SITE}/images/theme/nouveau/og-image.jpg"/>
    <meta property="og:site_name" content="Amthonie"/>
    <meta property="og:locale" content="en_GB"/>

    {jsonld}

    <!-- Precompiled Tailwind (built from src/input.css by the Pages workflow) -->
    <link rel="stylesheet" href="../styles.css"/>
    <!-- Hand-authored page styles (the "remember my tinkering" toggle). Static
         file, not a scoped <style> here — keeps this generator lean and renders
         in local preview without a Tailwind rebuild. -->
    <link rel="stylesheet" href="melodies.css"/>

    <!-- Umami tag -->
    <script defer src="https://cloud.umami.is/script.js" data-website-id="7ea47516-43a9-4ffe-b65d-52642e7b3c28" data-domains="amthonie.nl" data-tag="melodies"></script>
</head>

<body class="flex flex-col min-h-screen bg-paper text-stone-800 antialiased dark:bg-stone-900 dark:text-stone-100">
<a href="#main" class="skip-link">Skip to content</a>

<!-- Site banner: the branding box lives in a real <header> (banner landmark),
     outside <main> so the skip link and assistive tech can bypass it. -->
<header class="flex w-full flex-col items-center px-2.5 md:px-6 pt-6 md:pt-12">

    <!-- Header: banner image + branded band merged into one box (matches the home page).
         The Amthonie wordmark sits in the band with a back-home button; no subtitle or socials. -->
    <div class="w-full md:w-4/5 max-w-[1280px] overflow-hidden">
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
                    class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 aspect-square h-[150%] rounded-full object-cover bg-stone-800 ring-2 ring-stone-800"
                    draggable="false"
            />
        </a>
        <div class="flex items-center justify-between gap-6 bg-brand-600 dark:bg-brand-700 px-4 py-4 md:px-8 md:py-6">
            <h1 class="text-2xl md:text-3xl font-bold tracking-tight text-white">Amthonie <span class="font-normal text-white/70">|</span> Melodies</h1>
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

    {PAGE_NAV}

    <!-- RTTTL: intro (no title — the header band carries the page title) -->
    <section class="{SECTION_CLASS}">
        <p class="text-base font-semibold leading-relaxed text-stone-600 dark:text-stone-400">{DESCRIPTION_P1}</p>
        <p class="mt-3 text-base font-semibold leading-relaxed text-stone-600 dark:text-stone-400">{DESCRIPTION_P2}</p>
    </section>

    <!-- RTTTL: the collection — a brand title panel then one .panel per tune. -->
    {items}

    {TRY_IT_YOURSELF}

    {FORMAT_EXPLAINER}

</main>

<!-- Footer -->
<footer class="w-full mt-auto px-2.5 md:px-6 py-4 text-center text-xs text-stone-500 dark:text-stone-400">
    <nav class="site-nav center">
        <a href="/">Home</a>
        <span class="sep">·</span>
        <a href="/about/">About me</a>
        <span class="sep">·</span>
        <a href="/naarden/">About Naarden</a>
        <span class="sep">·</span>
        <a href="/naarden/weather/">Weather</a>
        <span class="sep">·</span>
        <a href="/jottings/">Jottings</a>
        <span class="sep">·</span>
        <a href="/melodies/">Melodies</a>
    </nav>
    <p>&copy; <span id="year"></span> Amthonie — <a href="/colophon/" class="hover:text-brand-600 dark:hover:text-brand-400 hover:underline transition">A light static site, minimal footprint</a></p>
</footer>

<script>
    document.getElementById('year').textContent = new Date().getFullYear();
</script>

<!-- RTTTL player (self-hosted; see vendor/rtttl-play/LICENSE) + page behaviour
     (button wiring and the opt-in "remember my tinkering" cookies) in the
     hand-authored melodies.js, loaded after the player so rtttlPlay exists. -->
<script src="../vendor/rtttl-play/index.umd.min.js"></script>
<script src="melodies.js"></script>

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
    MELODIES_PAGE.parent.mkdir(parents=True, exist_ok=True)
    MELODIES_PAGE.write_text(page, encoding="utf-8")
    print(f"wrote {MELODIES_PAGE.relative_to(ROOT)} ({len(posts)} tune(s))")


def _set_lastmod(text: str, loc: str, lastmod: str) -> str:
    """Update the <lastmod> of an existing <loc> in place (no-op if absent)."""
    return re.sub(
        rf"(<loc>{re.escape(loc)}</loc>\s*<lastmod>)[^<]*(</lastmod>)",
        rf"\g<1>{lastmod}\g<2>",
        text,
    )


def update_sitemap(posts: list[dict]) -> None:
    """Ensure a /melodies/ sitemap entry exists, lastmod = today.

    Unlike jottings/chronicle there's no per-tune date to derive this from, so
    the build date is the best available freshness signal — it only actually
    moves the needle when the generator runs as part of a real deploy. The
    home page's own lastmod is left untouched — its /melodies/ teaser is
    static, not generated from this content, so it never goes stale.
    """
    if not posts:
        return
    lastmod = datetime.now().strftime("%Y-%m-%d")
    loc = f"{SITE}/melodies/"
    text = SITEMAP.read_text(encoding="utf-8")

    if loc in text:
        text = _set_lastmod(text, loc, lastmod)
    else:
        entry = (
            "    <url>\n"
            f"        <loc>{loc}</loc>\n"
            f"        <lastmod>{lastmod}</lastmod>\n"
            "    </url>\n"
        )
        text = text.replace("</urlset>", entry + "</urlset>")

    SITEMAP.write_text(text, encoding="utf-8")
    print(f"sitemap.xml: /melodies/ lastmod {lastmod}")


def main() -> int:
    posts = load_posts()
    build_melodies_page(posts)
    update_sitemap(posts)
    return 0


if __name__ == "__main__":
    sys.exit(main())

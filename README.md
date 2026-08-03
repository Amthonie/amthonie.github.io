# amthonie.github.io

![](https://cloud.umami.is/p/UmHrKf2kJ)

A small personal website hosted with [GitHub Pages](https://pages.github.com/).

## Tech

- Static HTML — no framework, no client-side build step to run the site.
- [Tailwind CSS v4](https://tailwindcss.com/) for styling, compiled to a single stylesheet.
- Photo gallery at `/naarden/` using [PhotoSwipe](https://photoswipe.com/), self-hosted
  under `vendor/photoswipe/` at the repo root (no third-party CDN — see the note in
  `naarden/index.html` for how to update it). The lightbox is shared: the Chronicle
  article heroes reuse the same vendored copy. The old `/gallery/` URL is a permanent
  redirect stub to `/naarden/`.
- A dedicated **live weather page** at `/naarden/weather/` — current conditions,
  an hourly and three-day forecast, sun/moon times and a plain-language outlook.
  Data is pushed to a GitHub gist by a home-automation server on a schedule and
  fetched client-side; icons are [Meteocons](https://bas.dev/work/meteocons)
  (MIT), self-hosted under `vendor/meteocons/`. The Naarden page links to it with
  a compact live teaser (condition icon + temperature). See [Weather](#weather).
- `/jottings/` and `/chronicle/` are generated from markdown sources at build time
  (see [Generated pages](#generated-pages)).
- A custom `404.html` and `sitemap.xml`, plus JSON-LD structured data and Open Graph
  tags on every page.
- Deployed automatically via GitHub Actions on every push to `main`.

## Structure

```
.
├── index.html          # home page (Jottings teasers are generated — see below)
├── 404.html            # custom not-found page (root-absolute asset paths)
├── gallery/
│   └── index.html      # permanent redirect stub → /naarden/
├── naarden/
│   ├── index.html      # Naarden page + photo gallery + live-weather teaser link (served at /naarden/)
│   ├── weather/
│   │   ├── index.html  # live weather page (served at /naarden/weather/) — the card + forecast box
│   │   ├── weather.css # weather-card styles (scoped #weather .wx-*)
│   │   └── weather.js  # weather behaviour (fetches the gist: card, forecast box, and the /naarden/ teaser)
│   ├── images/         # full-size photos (~2048px long edge)
│   └── thumbnails/     # grid thumbnails (~640px wide)
├── vendor/
│   ├── photoswipe/     # self-hosted PhotoSwipe lightbox (shared: naarden + chronicle)
│   └── meteocons/      # self-hosted Meteocons weather icons (MIT)
├── jottings/
│   └── index.html      # jottings page (served at /jottings/) — GENERATED
├── chronicle/
│   ├── index.html      # Chronicle front page (served at /chronicle/) — GENERATED
│   ├── <slug>/         # one generated page per article (/chronicle/<slug>/) — GENERATED
│   ├── header.webp         # landing masthead image
│   ├── header-articles.webp  # slim per-article masthead banner
│   ├── icon.png            # the Chronicle's own favicon (navy TIC monogram)
│   ├── favicon.ico         # multi-resolution favicon (16/32/48)
│   └── images/         # per-article heroes (+ thumbs/ for the index cards)
├── content/
│   ├── jottings/       # markdown sources for jottings (one file per jotting)
│   └── chronicle/      # markdown sources for chronicle articles
├── scripts/
│   ├── build_jottings.py   # generates the jottings page + homepage teasers
│   └── build_chronicle.py  # generates the chronicle front page + per-article pages
├── src/input.css       # Tailwind entry point (source)
├── styles.css          # compiled stylesheet (committed)
├── images/             # shared static assets
├── sitemap.xml         # kept in sync by the generators
└── .github/workflows   # build & deploy pipeline
```

## Images

All images are **WebP**. The target sizes below are what the layout actually
needs — no larger, which is what keeps the pages loading instantly.

| Image | Location | Target size | Notes |
|---|---|---|---|
| **Link cards** | `images/links/` | **640×360** (16:9) | Shown in a 16:9 card with `object-cover`. Crop the source to 16:9 and nothing needs aligning. If it isn't 16:9, keep it as-is and add an `object-*` class (e.g. `object-bottom`, `object-left`) so the auto-crop keeps the important part — otherwise it centre-crops. |
| **Gallery photos** | `naarden/images/` | **2048px on the longest edge** (keep native aspect), quality ≈80 | Opened full-screen in the PhotoSwipe lightbox. Long-edge cap so portrait and landscape both fit the screen. Set each link's `data-pswp-width` / `data-pswp-height` to the photo's real pixel size, or the lightbox mis-sizes it. |
| **Gallery thumbnails** | `naarden/thumbnails/` | **640px wide** (keep native aspect), quality ≈75 | Shown 16:9 with `object-cover` (centre-cropped), so keep the subject roughly centred. Use the **same base filename** as the full photo. |
| **Jotting images** | `jottings/images/` | **~1536px on the longest edge** (keep native aspect), quality ≈80 | Optional per-jotting figure, referenced by the jotting's `image:` frontmatter (bare filename). Opens full-size in the PhotoSwipe lightbox (the generator reads the pixel size from the file, so there's no `data-pswp-*` to set by hand; falls back to a new tab if scripting is off). Floated beside the text on desktop; portrait images become a centred, capped inset on mobile, landscape ones go full-width. |
| **Jotting thumbnails** | `jottings/images/thumbnails/` | **640px on the longest edge** (keep native aspect), quality ≈75 | The image actually shown inline (the full-size is only the click target). Shown uncropped, so any aspect is fine. Use the **same base filename** as the full-size image; the card falls back to the full-size image if a thumbnail is missing. |
| **Chronicle heroes** | `chronicle/images/` | **~1024px on the longest edge** (any aspect), quality ≈80 | Per-article hero, referenced by the article's `image:` frontmatter (bare filename). Shown uncropped — floated beside the text on wide screens, full-width on mobile — and clickable to open full-size in the PhotoSwipe lightbox. The generator reads the pixel size from the file, so there's no `data-pswp-*` to set by hand. |
| **Chronicle index thumbnails** | `chronicle/images/thumbs/` | **480px wide**, quality ≈72 | Small teaser image leading each front-page index card. Use the **same base filename** as the hero; generate with e.g. `convert hero.webp -resize 480x -quality 72 thumbs/hero.webp`. The card falls back to the full hero if a thumbnail is missing. |
| **Chronicle favicon** | `chronicle/` | `icon.png` 512×512 + `favicon.ico` (16/32/48) | The Chronicle's own tab icon (a navy TIC monogram, rounded), distinct from the main site. `favicon.ico` is regenerated from `icon.png`: `convert icon.png -define icon:auto-resize=48,32,16 favicon.ico`. |

640px-wide link images match the desktop 3-column layout at 2× (retina). If you
ever want them sharper when a card is shown full-width on a high-DPI phone,
export at ~1280×720 — still only tens of KB as WebP.

## Generated pages

Two sections are generated from markdown at build time by sibling scripts in
`scripts/`, sharing the same frontmatter format: **Jottings** (`/jottings/`) and
**The Interplanetary Chronicle** (`/chronicle/`, a satirical, entirely fictional
outlet).

### Jottings

Jottings are plain markdown files under `content/jottings/`, one per jotting, each
starting with a small frontmatter block:

```markdown
---
id: 12
date: 2026-07-16
slug: a-short-headline
title: A short headline
summary: Optional one-line teaser for the homepage (defaults to the first paragraph).
image: 12-a-photo.webp
image_alt: What the photo shows (optional; defaults to the title)
image_caption: Optional caption shown under the image
image_side: right
---

The body is regular **markdown** — links, lists, etc.
```

**Frontmatter keys:** `id` (required), `date` (required, `YYYY-MM-DD`) and
`title` (required); everything else is optional. The on-page anchor for a
jotting (`/jottings/#<anchor>`) is composed as **`<id>-<slug>`** — e.g.
`12-a-short-headline`. The `id` is a stable numeric handle that namespaces the
anchor (so two jottings can share a slug without colliding); the `slug` is the
human-readable tail. **If `slug` is omitted it falls back to the (required)
title, slugified** — e.g. a title of *A short headline* yields `a-short-headline`.
(The title, not the filename, so the anchor is fully editable from a phone, where
files can't easily be renamed.) Setting the slug explicitly keeps the anchor tidy
when the title is long, or lets you retitle without moving the URL. The list is
ordered by `date`, not by `id` or filename.

**Optional image** (floated beside the note, like the Naarden and Chronicle
figures): set `image` to a **bare WebP filename** living in `jottings/images/`
(with a matching thumbnail in `jottings/images/thumbnails/` — see the image-prep
table above). The thumbnail is shown inline and opens the full-size image in the
PhotoSwipe lightbox (the same one used across the site; grouped per jotting, so
several images in one jotting swipe as a set). Orientation is auto-detected from
the file: a **portrait** image is shown as a centred inset at half the screen
width on mobile (rather than a full-width tower) and floats on desktop; a
**landscape** image is full-width on mobile like the other figures. Companion
keys, all optional: `image_alt` (defaults to the title),
`image_caption` (omit for none) and `image_side` (`right` — the default — or
`left`).

**Body links:** links in the markdown body that point off-site (an
`http(s)://` URL) are rewritten to open in a new tab (`target="_blank"
rel="noopener"`), matching the curated links on the home page; relative links
and in-page `#anchors` stay in the current tab. This applies to both jottings
and Chronicle article bodies — nothing to set per link.

`scripts/build_jottings.py` turns those into:

- `jottings/index.html` — the full list, newest first, served at `/jottings/`;
- the teaser cards on the home page (between the `<!-- JOTTINGS:START -->` /
  `<!-- JOTTINGS:END -->` markers in `index.html`);
- the `/jottings/` entry in `sitemap.xml` (its `lastmod` tracks the newest post).

To add a jotting: drop a new `.md` file in `content/jottings/` and push. The
deploy workflow runs the generator automatically, so you don't have to build
anything by hand. To preview locally, run it yourself (needs the `markdown`
package): `python3 scripts/build_jottings.py`. The generated `jottings/index.html`
is committed as a build artefact (like `styles.css`), so re-run the generator
and commit its output when you want the committed copy to stay current.

### The Interplanetary Chronicle

`/chronicle/` is a satirical, entirely fictional outlet. Its articles live in
`content/chronicle/*.md` (same frontmatter as jottings, plus one extra) and
`scripts/build_chronicle.py` turns them into:

- `chronicle/index.html` — the front page: a masthead plus an index of teaser
  cards (each leading with the article's thumbnail) linking to the articles;
- `chronicle/<slug>/index.html` — one standalone page per article, with its own
  `<title>`, canonical link, Open Graph tags and `SatiricalArticle` JSON-LD;
- the `/chronicle/` entry in `sitemap.xml`.

**Only the landing is indexed.** The article pages are marked `noindex,follow`
and kept out of the sitemap, so the front page is the single search entry point
and article slugs stay disposable — renaming or deleting one leaves no indexed
URL behind. Articles stay fully readable and shareable (noindex only affects
search listing, not access or link-preview cards). There is deliberately **no
RSS feed**: syndicating the satire as bare text would strip the framing that
marks it as fiction.

The one extra frontmatter key is an optional `image:` — a **bare filename** (no
path) of a WebP in `chronicle/images/`, shown as the per-article hero and, via a
matching thumbnail in `chronicle/images/thumbs/`, on the front-page card; omit it
for a text-only card. Unlike jottings, the Chronicle deliberately does **not**
touch the home page — the homepage links to it via a hand-written, static promo
box, so the satirical content never bleeds onto the main site. Preview it the
same way: `python3 scripts/build_chronicle.py`.

`content/` and `scripts/` are build inputs and are excluded from the published
site. The markdown content itself is never served raw.

## Weather

A dedicated **live weather page** at `/naarden/weather/` shows current
conditions, an hourly and three-day forecast, sun/moon times and a plain-language
outlook. It's a pull-based design that keeps the site fully static:

- A home-automation server (Home Assistant) pushes a small JSON snapshot to a
  **GitHub gist** on a schedule — nothing runs server-side here.
- `naarden/weather/weather.js` fetches that gist client-side and populates the
  `#weather` card in `naarden/weather/index.html`; `naarden/weather/weather.css`
  styles it (scoped to `#weather`, light/dark via `prefers-color-scheme`).
- The card body is one grid of six blocks — condition, temp+wind, hourly
  forecast, daily forecast, sun times, moon phase — one column on small screens,
  two from 1020px up, with a full-width rule between the current / forecast /
  astro pairs.
- Weather icons are [Meteocons](https://bas.dev/work/meteocons) (MIT),
  self-hosted under `vendor/meteocons/` — no third-party CDN.
- The card's footer carries a **source note** ("Sourced from my Home Assistant")
  beside the JS-driven "Updated …" freshness stamp.

**Forecast in words.** The page's title box leads with a plain-language forecast
paragraph beneath the `<h1>`. The text is a second file (`forecast_naarden.txt`)
in the **same gist**; `weather.js` fetches it independently of the JSON card (so
one failing doesn't hide the other) and drops it in with `textContent`. The
heading is always shown; the paragraph appears only once the text loads.

**Teaser on the Naarden page.** `/naarden/` doesn't embed the card — it shows a
compact link box (driven by the same `weather.js`, via a guarded code path) with
the live condition icon + temperature, linking through to the weather page. The
box is revealed only when the gist has data, so a failed/empty fetch just leaves
it hidden — nothing to click through to.

**Weather maps.** Below the card, a collapsible board shows KNMI forecast maps
(`cdn.knmi.nl`), picked by time of day (Europe/Amsterdam): before 18:00 → current
+ today + tonight + tomorrow; from 18:00 → current + tonight + tomorrow +
tomorrow-night. It's **collapsed by default behind a Show/Hide toggle** and the
maps — third-party images — are fetched only on first expand, so no request
reaches KNMI (and no visitor IP is exposed) until the visitor opts in. How many
show tracks the column count (1–2 columns → 2 maps, 3 → 3, 4 → 4); the extra
slots are `lazy`, so narrow screens don't fetch them. The maps carry their own
"Bron: KNMI" label and link to KNMI's forecast page, with a "Maps source:
knmi.nl" credit under the heading. The title and credit stay visible whether the
board is open or closed.

The behaviour is deliberately forgiving: missing fields are skipped, and if the
fetch fails the card, forecast paragraph and teaser simply stay hidden rather
than rendering broken. Icon paths are root-absolute (`/vendor/meteocons/…`), so
the script works at any page depth.

## Local development

The compiled `styles.css` is committed, so most pages can be opened directly
from disk. To browse the site the way it's actually served — with absolute
paths resolving from the site root — run a static server from the repo root:

```bash
python3 -m http.server 4599
# then open http://localhost:4599/
```

Prefer this over `file://` for anything that uses **absolute** asset paths. In
particular the **404 page does not render from disk**: `404.html` links its CSS
and images with root-absolute paths (`/styles.css`, `/images/…`) so it stays
styled when GitHub Pages serves it for a missing URL at any depth — and those
only resolve over HTTP. Preview it at `http://localhost:4599/404.html`, not by
opening the file.

To rebuild the stylesheet after changing HTML or `src/input.css`, run the
Tailwind CLI against the input file and output to `styles.css`.

Tailwind only scans the files listed via `@source` in `src/input.css`, so when
adding a **new** HTML page, register it there too (currently `index.html`,
`naarden/index.html`, `naarden/weather/index.html`, `jottings/index.html`,
`chronicle/index.html`, the `chronicle/*/index.html` article pages and
`404.html` are listed) — otherwise
its utility classes are dropped from the build.

### Production-parity preview

To preview the site **exactly as GitHub Pages builds and serves it** — both
generators run, `_site/` assembled with the same exclusions, Tailwind rebuilt —
use the helper script instead of serving the repo root:

```bash
scripts/build-site.sh             # build _site/ only
scripts/build-site.sh --serve     # build, then serve http://localhost:4599
```

It mirrors the steps in `.github/workflows/deploy.yml`, so what you see is what
deploys — the custom 404 and root-absolute paths included. The generators write
their regenerated output back into the working tree (as they do in CI), and it
downloads a pinned standalone Tailwind CLI on first run (gitignored). Keep the
`TAILWIND_VERSION` in the script in sync with the workflow.

## Deployment

Pushing to `main` triggers the GitHub Actions workflow, which assembles the
static files, (re)builds the Tailwind stylesheet when needed, and publishes the
result to GitHub Pages. Deployments can also be triggered manually from the
Actions tab.

## Cleaning up local build artefacts

A few things are generated **locally** by `scripts/build-site.sh` and kept out
of git (all gitignored). None are needed to run or deploy the site — CI builds
its own copies on the runner — so you can delete any of them at any time and the
next local build recreates them:

| Path | What it is |
|---|---|
| `tailwindcss` | The pinned standalone Tailwind CLI (~107 MB), downloaded on first build and reused thereafter. |
| `_site/` | A full, production-parity copy of the assembled site (exactly what GitHub Pages serves) from the last local build — pages, `styles.css`, images, `vendor/`, etc., minus the build inputs (`src/`, `content/`, `scripts/`, `.github/`). |
| `.venv/` | Python virtualenv holding the `markdown` package the page generators need. |

```bash
rm -rf tailwindcss _site .venv    # all safe — regenerated on the next build
```

**Upgrading Tailwind — you must delete the binary.** The build downloads
`tailwindcss` only when it's missing (`if [ ! -x ./tailwindcss ]`), so bumping
`TAILWIND_VERSION` in `scripts/build-site.sh` (keep it in sync with
`.github/workflows/deploy.yml`) does **not** re-fetch on its own — the build
keeps reusing the stale binary. Remove it so the next build pulls the new
version:

```bash
rm -f tailwindcss    # then the next build fetches the pinned version
```

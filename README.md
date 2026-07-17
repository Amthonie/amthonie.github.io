# amthonie.github.io

A small personal website hosted with [GitHub Pages](https://pages.github.com/).

## Tech

- Static HTML — no framework, no client-side build step to run the site.
- [Tailwind CSS v4](https://tailwindcss.com/) for styling, compiled to a single stylesheet.
- Photo gallery at `/gallery/` using [PhotoSwipe](https://photoswipe.com/) (loaded as
  an ES module from a CDN; can be self-hosted — see the note in `gallery/index.html`).
- Deployed automatically via GitHub Actions on every push to `main`.

## Structure

```
.
├── index.html         # home page (Updates teasers are generated — see below)
├── gallery/
│   ├── index.html     # gallery page (served at /gallery/)
│   ├── images/        # full-size photos (~2048px long edge)
│   └── thumbnails/    # grid thumbnails (~640px long edge)
├── updates/
│   └── index.html     # updates page (served at /updates/) — GENERATED
├── content/updates/   # markdown sources for the updates (one file per update)
├── scripts/
│   └── build_updates.py  # generates the updates page + homepage teasers
├── src/input.css      # Tailwind entry point (source)
├── styles.css         # compiled stylesheet (committed)
├── images/            # shared static assets
└── .github/workflows  # build & deploy pipeline
```

## Images

All images are **WebP**. The target sizes below are what the layout actually
needs — no larger, which is what keeps the pages loading instantly.

| Image | Location | Target size | Notes |
|---|---|---|---|
| **Link cards** | `images/links/` | **640×360** (16:9) | Shown in a 16:9 card with `object-cover`. Crop the source to 16:9 and nothing needs aligning. If it isn't 16:9, keep it as-is and add an `object-*` class (e.g. `object-bottom`, `object-left`) so the auto-crop keeps the important part — otherwise it centre-crops. |
| **Gallery photos** | `gallery/images/` | **2048px on the longest edge** (keep native aspect), quality ≈80 | Opened full-screen in the PhotoSwipe lightbox. Long-edge cap so portrait and landscape both fit the screen. Set each link's `data-pswp-width` / `data-pswp-height` to the photo's real pixel size, or the lightbox mis-sizes it. |
| **Gallery thumbnails** | `gallery/thumbnails/` | **640px wide** (keep native aspect), quality ≈75 | Shown 16:9 with `object-cover` (centre-cropped), so keep the subject roughly centred. Use the **same base filename** as the full photo. |

640px-wide link images match the desktop 3-column layout at 2× (retina). If you
ever want them sharper when a card is shown full-width on a high-DPI phone,
export at ~1280×720 — still only tens of KB as WebP.

## Updates / news

Updates are plain markdown files under `content/updates/`, one per update, each
starting with a small frontmatter block:

```markdown
---
date: 2026-07-16
title: A short headline
summary: Optional one-line teaser for the homepage (defaults to the first paragraph).
---

The body is regular **markdown** — links, lists, etc.
```

`scripts/build_updates.py` turns those into:

- `updates/index.html` — the full list, newest first, served at `/updates/`;
- the teaser cards on the home page (between the `<!-- UPDATES:START -->` /
  `<!-- UPDATES:END -->` markers in `index.html`);
- the `/updates/` entry in `sitemap.xml` (its `lastmod` tracks the newest post).

To add an update: drop a new `.md` file in `content/updates/` and push. The
deploy workflow runs the generator automatically, so you don't have to build
anything by hand. To preview locally, run it yourself (needs the `markdown`
package): `python3 scripts/build_updates.py`. The generated `updates/index.html`
is committed as a build artifact (like `styles.css`), so re-run the generator
and commit its output when you want the committed copy to stay current.

`content/` and `scripts/` are build inputs and are excluded from the published
site. The markdown content itself is never served raw.

## Local development

The compiled `styles.css` is committed, so the site can be opened directly.
To rebuild the stylesheet after changing HTML or `src/input.css`, run the
Tailwind CLI against the input file and output to `styles.css`.

Tailwind only scans the files listed via `@source` in `src/input.css`, so when
adding a **new** HTML page, register it there too (both `index.html` and
`gallery/index.html` are currently listed) — otherwise its utility classes are
dropped from the build.

## Deployment

Pushing to `main` triggers the GitHub Actions workflow, which assembles the
static files, (re)builds the Tailwind stylesheet when needed, and publishes the
result to GitHub Pages. Deployments can also be triggered manually from the
Actions tab.

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
├── index.html         # home page
├── gallery/
│   ├── index.html     # gallery page (served at /gallery/)
│   ├── images/        # full-size photos (~2048px long edge)
│   └── thumbnails/    # grid thumbnails (~640px long edge)
├── src/input.css      # Tailwind entry point (source)
├── styles.css         # compiled stylesheet (committed)
├── images/            # shared static assets
└── .github/workflows  # build & deploy pipeline
```

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

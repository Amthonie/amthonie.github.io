# amthonie.github.io

Personal profile / landing page for **amthonie.nl**, served via GitHub Pages.

## What this is

- A single static page: [`index.html`](index.html). No build step, no framework.
- Styled with **Tailwind CSS via the Play CDN** (`<script src="cdn.tailwindcss.com">`) — fine for a page this size. Tailwind config is inline in the `<head>`.
- Dark UI: `darkMode: 'class'` with `class="dark"` hard-set on `<html>`, and a fixed OKLCH gradient background (black → brand orange) on `<body>`.
- Brand accent orange is `#FF7A00` (matches the favicon).
- Images live in [`images/`](images/); link-card thumbnails in [`images/links/`](images/links/).

## Hosting

- GitHub Pages serves from the **`main`** branch.
- Custom domain **amthonie.nl** is set via the [`CNAME`](CNAME) file + repo Pages settings; DNS (A/AAAA + `www` CNAME) is managed at the registrar. HTTPS enforcement is on.
- Merging to `main` publishes the site.

## Working agreements

- **Always work on a branch — never commit straight to `main`.** Name it `YYYYMMDD-concise-title` (e.g. `20260707-init`, `20260707-add-links`). Open a PR into `main`.
- In **this repo** it's fine to include a "Generated with Claude Code" line in commit messages.
- Every commit message should include a **concise description of the changes** (not just a title).

## Conventions worth keeping

- **Compress images before committing.** Source screenshots/photos are often 1–2 MB; resize to ~1200px wide and re-encode (Pillow works well) so thumbnails land around 50–150 KB. Photos → JPEG; logos/line art → keep SVG (crisp, tiny).
- **Link cards** are a 2×2 grid; each thumbnail is `aspect-[16/9]`. A card is an `<a>` wrapping a thumbnail + title + description. Duplicate an existing card block to add one.
- Layered thumbnails (photo + overlaid logo) are done with absolutely-positioned `<img>` layers so SVG logos stay sharp — see the SZB and Home Assistant cards.
- The header banner and content boxes use `w-[90%] md:w-4/5 max-w-[1024px]` so they're wider on phones, capped on desktop.

## Previewing locally

No server needed to edit, but to view it as served:

```
python3 -m http.server 4173
```

then open http://localhost:4173/.

#!/usr/bin/env bash
#
# build-site.sh — build the site into ./_site the same way the GitHub Pages
# workflow (.github/workflows/deploy.yml) does, then optionally serve it, so you
# can preview uncommitted changes exactly as they'll deploy.
#
# It mirrors the deploy job's build steps:
#   1. ensure a Python venv with `markdown`, then run both page generators
#   2. assemble ./_site from the working tree — same exclusions as CI, and it
#      honours .gitignore, so local-only files (.venv, .idea, …) aren't copied
#   3. (re)build the Tailwind stylesheet into _site/styles.css with the pinned
#      standalone CLI
#
# Notes:
#   - The generators write the regenerated pages back into the working tree
#     (jottings/, chronicle/, the homepage teasers, sitemap.xml) — exactly as in
#     CI. Commit or discard those as you see fit.
#   - Serving from _site/ (not the repo root) means root-absolute paths and the
#     custom 404 behave just like they do on GitHub Pages.
#   - _site/ and the downloaded ./tailwindcss binary are gitignored.
#   - This script is a LOCAL convenience only — the deploy workflow inlines its
#     own equivalent steps and never calls it, so it's safe to change.
#
# Usage:
#   scripts/build-site.sh                   full build into _site/ (no server)
#   scripts/build-site.sh --serve           full build, then serve _site/ on http://localhost:4599
#   scripts/build-site.sh --css             quick: recompile the repo-root styles.css only (see below)
#   PORT=8080 scripts/build-site.sh --serve serve on a different port
#
# About --css:
#   The always-on preview (systemd service `amthonie.service`,
#   http://localhost:4599) serves the REPO-ROOT working tree, and therefore the
#   committed repo-root styles.css. Tailwind v4 only emits CSS for the utility
#   classes it finds when it scans the HTML, so after you add or change a class
#   in the HTML — especially a new arbitrary value such as a bracketed height
#   percentage — that class has NO rule in the stale committed styles.css and
#   appears to do nothing.
#   (Deliberately no literal example class here: Tailwind's auto content
#   detection scans this .sh file too, and any real class literal written in a
#   comment would get emitted as an unused rule — even into the production CSS.)
#   `--css` recompiles src/input.css -> ./styles.css (repo root) so the running
#   4599 preview picks the change up on reload. It skips the _site assembly and
#   the page generators, so it's near-instant.
#   (For a live loop, the standalone CLI also supports --watch:
#    ./tailwindcss -i src/input.css -o styles.css --watch)

set -euo pipefail

# Keep this in sync with the version pinned in .github/workflows/deploy.yml.
TAILWIND_VERSION="v4.3.2"
PORT="${PORT:-4599}"
SERVE=0
CSS_ONLY=0
for arg in "$@"; do
    case "$arg" in
        --serve) SERVE=1 ;;
        --css)   CSS_ONLY=1 ;;
        *) echo "Unknown option: $arg (see the usage comment at the top of this script)" >&2; exit 2 ;;
    esac
done

# Always run from the repo root, regardless of where this is invoked from.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Download the standalone CLI once, then reuse it (it's gitignored). Self-
# contained (bundles the tailwindcss package) so it needs no Node/node_modules.
ensure_tailwind() {
    if [ ! -x ./tailwindcss ]; then
        case "$(uname -s)" in
            Linux)  os=linux ;;
            Darwin) os=macos ;;
            *) echo "Unsupported OS $(uname -s); download the tailwindcss CLI manually." >&2; exit 1 ;;
        esac
        case "$(uname -m)" in
            x86_64|amd64)  arch=x64 ;;
            aarch64|arm64) arch=arm64 ;;
            *) echo "Unsupported arch $(uname -m); download the tailwindcss CLI manually." >&2; exit 1 ;;
        esac
        url="https://github.com/tailwindlabs/tailwindcss/releases/download/${TAILWIND_VERSION}/tailwindcss-${os}-${arch}"
        echo "    downloading ${url}"
        curl -fsSL -o tailwindcss "$url"
        chmod +x tailwindcss
    fi
}

# --css: quick path for the always-on 4599 preview. Recompile ONLY the repo-root
# styles.css that the systemd service serves, then exit. No generators, no _site.
if [ "$CSS_ONLY" = "1" ]; then
    echo "==> Build Tailwind CSS -> styles.css (repo root, for the http://localhost:${PORT}/ preview)"
    ensure_tailwind
    ./tailwindcss -i src/input.css -o styles.css --minify
    echo "==> Done. Reload http://localhost:${PORT}/ to see the change."
    exit 0
fi

echo "==> 1/3  Python venv + page generators"
if [ ! -x .venv/bin/python ]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --quiet markdown
.venv/bin/python scripts/build_jottings.py
.venv/bin/python scripts/build_chronicle.py

echo "==> 2/3  Assemble _site/ (working tree, minus build inputs & gitignored files)"
rm -rf _site
# --filter ':- .gitignore' makes rsync skip everything git ignores (incl. _site
# itself, avoiding recursion). The explicit excludes are the build inputs that
# CI drops but git tracks. This matches the rsync step in deploy.yml.
rsync -a \
    --filter=':- .gitignore' \
    --exclude='.git/' \
    --exclude='.github/' \
    --exclude='src/' \
    --exclude='content/' \
    --exclude='scripts/' \
    ./ _site/

echo "==> 3/3  Build Tailwind CSS -> _site/styles.css"
ensure_tailwind
./tailwindcss -i src/input.css -o _site/styles.css --minify

echo "==> Done. _site/ is ready."

if [ "$SERVE" = "1" ]; then
    echo "==> Serving http://localhost:${PORT}/  (Ctrl-C to stop)"
    cd _site
    exec python3 -m http.server "$PORT"
fi

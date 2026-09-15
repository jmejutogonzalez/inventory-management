# Factory Inventory Management System - task runner
# Run `just` with no arguments to list recipes.

set shell := ["bash", "-cu"]

docs_dir := "ignored_docs"
diagrams_dir := docs_dir / "diagrams"

# List available recipes
default:
    @just --list

# Install backend (uv) and frontend (npm) dependencies
install:
    cd server && uv sync
    cd client && npm install

# Start the FastAPI backend on :8001 (foreground)
backend:
    cd server && uv run python main.py

# Start the Vite frontend on :3000 (foreground)
frontend:
    cd client && npm run dev

# Start both servers; Ctrl+C stops both
dev: stop
    #!/usr/bin/env bash
    set -euo pipefail
    (cd server && uv run python main.py) &
    (cd client && npm run dev) &
    # Kill both children when this recipe is interrupted, otherwise they outlive `just`.
    trap 'kill $(jobs -p) 2>/dev/null' INT TERM EXIT
    wait

# Kill anything listening on the dev ports
stop:
    -lsof -ti:3000,8001 | xargs kill -9 2>/dev/null

# Run backend API tests
test:
    @# tests/ has no pyproject of its own, so borrow the server's uv environment.
    cd tests && uv run --project ../server pytest backend -v

# Open the running frontend and API docs in the default browser
open:
    open http://localhost:3000
    open http://localhost:8001/docs

# Render Mermaid sources (*.mmd) in ignored_docs/diagrams to SVG
diagrams:
    #!/usr/bin/env bash
    set -euo pipefail
    cd {{diagrams_dir}}
    # mermaid-cli needs a headless Chrome; reuse the local install instead of a puppeteer download.
    for f in *.mmd; do
        echo "rendering $f"
        mmdc -q -p puppeteer-config.json -i "$f" -o "${f%.mmd}.svg" -t neutral -b white
    done

# Render diagrams and open the architecture docs
docs: diagrams
    open {{docs_dir}}/architecture.html
    open {{docs_dir}}/ARCHITECTURE.md

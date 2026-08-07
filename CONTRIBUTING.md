# Contributing to Manim Dock

Thanks for helping. Keep the [invasion test](docs/invasion-test.md) green.

## Dev setup

1. Python sidecar: `cd python && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
2. Extension: `npm install && npm run compile`
3. Launch **Run Manim Dock Extension** from the debug panel
4. Optional package check: `npm run package` (must include `python/manim_dock`, `media/konva.min.js`, `templates/`, `snippets/`)

## Project agents

When changing behavior, consider delegating to:

- `invasion-guardian` — product law
- `creator-ux` — dual-surface workflow
- `manim-affinity` — real Manim / VGroup affinity
- `sidecar-python` — parser/patches

## PR checklist

- [ ] Plain ManimCE examples still run without the extension
- [ ] No required Dock scene base class
- [ ] Tests updated for parser/patch changes
- [ ] UX degrade path when parse is incomplete

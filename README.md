# Manim Dock

**Manim Dock** (`manim-dock`) is an open-source VS Code companion for [Manim Community](https://www.manim.community/) educational video production.

It docks Outline, Stage, and Timeline tools beside your normal Manim Python — so layout and timing stop being pure trial-and-error — while coding facilitation (snippets, templates, libraries) speeds up structure and reuse.

> For people who **write Manim**. Not a no-code replacement for learning Python.

## Status

Phase 0–1 scaffold: Outline view, Doctor, **Render Scene (QL)** + thin video preview.

Requires ManimCE on PATH (or `python -m manim`) for rendering. Sideview remains optional for a richer player.

## Product pillars

1. **Stage + Timeline** — drag layout, tune pacing; surgical edits to real `.py`
2. **Coding facilitation** — educational snippets/templates, section scaffolds, library extract

## Non-negotiables

- Python / ManimCE is the **only** source of truth
- No required plugin scene base class; uninstall-safe
- Hard structure (`VGroup` construction, updaters, custom logic) stays in code
- Jupyter is out of V1 scope (small-loop testing via sections/methods + Stage instead)
- Preview: thin built-in video; coexist with [Manim Sideview](https://marketplace.visualstudio.com/items?itemName=Rickaym.manim-sideview)

## Repository layout

```text
├── package.json          # VS Code extension
├── src/                  # Extension host (TypeScript)
├── webview/              # Stage / Timeline UI (later)
├── python/               # Sidecar: outline, patches, doctor
├── examples/             # Sample ManimCE lessons
├── snippets/             # Educational snippet stubs
├── docs/                 # Architecture & product law
└── .cursor/              # Project agents & rules
```

## Quick start (development)

### Python sidecar

```bash
cd python
python3 -m venv .venv && source .venv/bin/activate   # if available
pip install -e ".[dev]"                              # pulls libcst + pytest
pytest
# Or without install / pytest:
PYTHONPATH=. python3 -m unittest discover -s tests -v
PYTHONPATH=. python3 -m manim_dock.cli outline ../examples/minimal_lesson/lesson.py
PYTHONPATH=. python3 -m manim_dock.cli doctor
```

### VS Code extension

```bash
npm install
npm run compile
# Then: Run Extension (F5) — launch config "Run Manim Dock Extension"
# Open examples/minimal_lesson/lesson.py and check the Manim Dock Outline view
```

## License

MIT — see [LICENSE](LICENSE).

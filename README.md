# Manim Dock

**Manim Dock** (`manim-dock`) is an open-source VS Code companion for [Manim Community](https://www.manim.community/) educational video production.

It docks Outline, Stage, and Timeline tools beside your normal Manim Python — so layout and timing stop being pure trial-and-error — while coding facilitation (snippets, templates, libraries) speeds up structure and reuse.

> For people who **write Manim**. Not a no-code replacement for learning Python.

## Status

**V1 (`v0.0.1`):** Outline, Doctor, QL + section-aware render, Stage, Timeline (pace/reorder/scrub), Properties (shift/buff/scale/duration), library extract, templates/snippets, editor↔surface sync. Plan: [docs/v1-architecture-plan.md](docs/v1-architecture-plan.md).

Requires ManimCE on PATH (or `python -m manim`) for rendering. Sideview remains optional for a richer player — see [docs/sideview.md](docs/sideview.md).

**Try Stage / Timeline:** open `examples/minimal_lesson/lesson.py` → **Open Stage** / **Open Timeline** → drag → confirm-diff → Apply.

**Try templates:** copy from `templates/` (`basic_scene.py`, `multi_section_scene.py`, `multi_scene_project.py`), or `python -m manim_dock.cli scaffold-example DEST`.

**Try library extract (P15):** Outline → right-click a method (e.g. `title_card`) → **Extract Method to Library**, or use `examples/lesson_lib` + `examples/lesson_with_lib/lesson.py` (`PYTHONPATH=examples`).

Architecture plan (in-repo): [docs/v1-architecture-plan.md](docs/v1-architecture-plan.md).

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
├── media/                # Extension icons + vendored Konva
├── python/               # Sidecar: outline, layout, patches, doctor, render
├── examples/             # Sample ManimCE lessons
├── templates/            # File templates (basic / multi-section / multi-scene)
├── snippets/             # Educational snippet stubs
├── docs/                 # Architecture, V1 plan, Sideview coexistence
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

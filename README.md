# Manim Dock

**Manim Dock** (`manim-dock`) is an open-source VS Code companion for [Manim Community](https://www.manim.community/) educational video production.

It docks Outline, Stage, and Timeline tools beside your normal Manim Python — so layout and timing stop being pure trial-and-error — while coding facilitation (snippets, templates, libraries) speeds up structure and reuse.

> For people who **write Manim**. Not a no-code replacement for learning Python.

## Status

**Current release tag:** `v0.0.2` (V2). **V3 implemented on main (unreleased)** — see [v3-roadmap.md](docs/v3-roadmap.md).

- V1 (`v0.0.1`): Outline, Doctor, Stage, Timeline, Properties, extract, templates — [plan](docs/v1-architecture-plan.md)
- V2 (`v0.0.2`): `patchMode`, VSIX, font_size/lag_ratio, align/distribute, scrub, P07–P10, library browser, render-method — [roadmap](docs/v2-roadmap.md)
- V3 (`v0.2.0` unreleased): Stage ctor-chain/`next_to`/`arrange` heuristics; Insert Wait/Play; Open in Sideview; doctor version matrix — [roadmap](docs/v3-roadmap.md)

Requires ManimCE on PATH (or `python -m manim`) for rendering. Sideview remains optional for a richer player — see [docs/sideview.md](docs/sideview.md).

**Try Stage / Timeline:** open `examples/minimal_lesson/lesson.py` → **Open Stage** / **Open Timeline** → drag → apply (confirm-diff, or set `manimDock.patchMode` to `auto`).

**Try Timeline insert / Sideview:** Timeline → select a beat → **Insert wait** / **Insert play**, or Command Palette **Manim Dock: Insert Wait** / **Insert Play Scaffold**. For a richer player: **Manim Dock: Open in Sideview** (installs/forwards to [Manim Sideview](https://marketplace.visualstudio.com/items?itemName=Rickaym.manim-sideview)).

**Try templates:** Command **Manim Dock: Insert Template**, or copy from `templates/`, or **Scaffold Example Project**.

**Try library extract (P15):** Outline → right-click a method (e.g. `title_card`) → **Extract Method to Library**, or use `examples/lesson_lib` + `examples/lesson_with_lib/lesson.py` (`PYTHONPATH=examples`).

Plans (in-repo): [V1](docs/v1-architecture-plan.md) · [V2 roadmap](docs/v2-roadmap.md) · [Validation checklist](docs/validation-checklist.md).

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

### VS Code extension (development)

```bash
npm install
npm run compile
# Then: Run Extension (F5) — launch config "Run Manim Dock Extension"
# Open examples/minimal_lesson/lesson.py and check the Manim Dock Outline view
```

### Install from VSIX

```bash
npm install
npm run package          # writes manim-dock-0.1.0.vsix
# Cursor / VS Code: Extensions → ⋯ → Install from VSIX…
```

Set `manimDock.pythonPath` to an interpreter that can `import manim` (and has `libcst` for patches: `pip install libcst`).

Optional: Settings → **Manim Dock: Patch Mode** → `auto` for drag→apply without confirm-diff (Undo still works).

## License

MIT — see [LICENSE](LICENSE).

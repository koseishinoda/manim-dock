# manim-dock (Python sidecar)

Parses ManimCE scene files, builds a Stage layout view model, and proposes surgical
source patches for the VS Code extension. The host always confirms before writing.

## CLI

```bash
python -m manim_dock.cli outline path/to/scene.py
python -m manim_dock.cli layout path/to/scene.py SceneName
python -m manim_dock.cli propose-shift path/to/scene.py title --dx 0.5 --dy -0.2
python -m manim_dock.cli timeline path/to/scene.py SceneName
python -m manim_dock.cli propose-duration path/to/scene.py play 47 --duration 1.5
python -m manim_dock.cli render path/to/scene.py SceneName --quality l
python -m manim_dock.cli doctor
```

## Design

- Outline / layout / timeline read: stdlib `ast` (no Manim import)
- Patches: `libcst` propose-only; prefer relative `shift` / axis vectors (G4)
- Timing: edit literal `run_time=` / `wait(n)`; module constants stay code-owned
- Layout positions are heuristics for the Stage canvas — never project truth

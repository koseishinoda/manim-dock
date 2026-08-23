# manim-dock (Python sidecar)

Parses ManimCE scene files for Outline / Timeline, captures Manim stills for Stage,
and proposes surgical timing patches for the VS Code extension. The host confirms
before writing (unless `manimDock.patchMode` is `auto`).

## CLI

```bash
python -m manim_dock.cli outline path/to/scene.py
python -m manim_dock.cli timeline path/to/scene.py SceneName
python -m manim_dock.cli snapshot path/to/scene.py SceneName 47
python -m manim_dock.cli propose-duration path/to/scene.py play 47 --duration 1.5
python -m manim_dock.cli propose-reorder path/to/scene.py 47 49
python -m manim_dock.cli extract-method path/to/scene.py SceneName method_name path/to/lib.py
python -m manim_dock.cli render path/to/scene.py SceneName --quality l
python -m manim_dock.cli serve
```

## Design

- Outline / timeline read: stdlib `ast` (no Manim import)
- Stage stills: temp early-exit + `manim -ql -s` (`snapshot_at_line`); cache by source hash
- Patches: `libcst` propose-only for duration / reorder
- Extract: Scene method → plain library `def foo(scene): …` (no Dock APIs)
- No AST Stage layout VM — Stage shows Manim rasters only

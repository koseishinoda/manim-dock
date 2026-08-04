# manim-dock (Python sidecar)

Parses ManimCE scene files and (later) applies surgical source patches for the VS Code extension.

## CLI

```bash
python -m manim_dock.cli outline path/to/scene.py
python -m manim_dock.cli doctor
```

## Design

- Outline/read: stdlib `ast`
- Patches (later): `libcst`
- No Manim import required for outline parsing

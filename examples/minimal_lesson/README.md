# Minimal lesson example

Plain ManimCE scene covering V1 patterns P01–P06 and P11–P12.

```bash
# Outline (no manim required)
cd ../../python && PYTHONPATH=. python3 -m manim_dock.cli outline ../examples/minimal_lesson/lesson.py

# Render via Dock sidecar (requires manim)
cd ../../python && PYTHONPATH=. python3 -m manim_dock.cli render ../examples/minimal_lesson/lesson.py MinimalLesson

# Or plain ManimCE
manim -ql lesson.py MinimalLesson
```

In Cursor (with Manim Dock installed/reloaded): open `lesson.py` → command **Manim Dock: Render Scene (QL)**, or click the play icon on the scene in Outline.

No Manim Dock imports — uninstall-safe by construction.

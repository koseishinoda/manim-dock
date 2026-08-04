# Minimal lesson example

Plain ManimCE scene covering V1 patterns P01–P06 and P11–P12.

```bash
# Outline (no manim required)
cd ../../python && PYTHONPATH=. python3 -m manim_dock.cli outline ../examples/minimal_lesson/lesson.py

# Render (requires manim)
manim -pql lesson.py MinimalLesson
```

No Manim Dock imports — uninstall-safe by construction.

# lesson_lib

Plain ManimCE helpers for educational patterns (P01–P03, P06).

**Not an extension dependency.** Copy this folder into your project, or add
`examples/` to `PYTHONPATH`, then:

```python
from lesson_lib import title_card, definition_card, PRIMARY

class MyScene(Scene):
    def construct(self):
        title_card(self, "Hook?")
        definition_card(self, body="…", color=PRIMARY)
```

Manim Dock can also extract a scene method into a library module via
**Manim Dock: Extract Method to Library** (confirm-diff; still plain Python).

# lesson_lib

Plain ManimCE helpers for educational patterns (P01–P03, P06–P10).

**Not an extension dependency.** Copy this folder into your project, or add
`examples/` to `PYTHONPATH`, then:

```python
from lesson_lib import title_card, definition_card, brace_callout, PRIMARY

class MyScene(Scene):
    def construct(self):
        title_card(self, "Hook?")
        definition_card(self, body="…", color=PRIMARY)
```

Helpers include:

| Helper | Pattern |
|--------|---------|
| `title_card` | P01 |
| `definition_card` | P02 |
| `step_list` | P03 |
| `two_column` | P06 |
| `brace_callout` | P07 |
| `axes_intro` | P08 |
| `compare_cards` | P09 |
| `succession_beat` | P10 |

Manim Dock can also extract a scene method into a library module via
**Manim Dock: Extract Method to Library** (confirm-diff; still plain Python),
and browse helpers via the library catalog (`library-catalog` / `library_catalog`).

from pathlib import Path

from manim_dock.layout import FRAME_HEIGHT, FRAME_WIDTH, parse_file_layout, parse_scene_layout

ROOT = Path(__file__).resolve().parents[2]
LESSON = ROOT / "examples" / "minimal_lesson" / "lesson.py"


def test_lesson_layout_finds_title_and_steps():
    layout = parse_file_layout(LESSON, "MinimalLesson")
    assert not layout.errors
    names = {i.name for i in layout.items}
    assert "title" in names
    assert "steps" in names
    assert "eq" in names

    title = next(i for i in layout.items if i.name == "title")
    assert title.editable
    assert any(c.kind == "to_edge" for c in title.layout_calls)
    assert title.y > 2.0  # near top edge


def test_move_to_origin_estimate():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        eq = MathTex("a")
        eq.move_to(ORIGIN)
'''
    layout = parse_scene_layout(source, "<mem>", "Demo")
    eq = next(i for i in layout.items if i.name == "eq")
    assert abs(eq.x) < 1e-9
    assert abs(eq.y) < 1e-9


def test_frame_aspect():
    assert abs(FRAME_WIDTH / FRAME_HEIGHT - 16 / 9) < 1e-9

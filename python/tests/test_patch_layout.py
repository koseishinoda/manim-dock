from manim_dock.patch_layout import propose_shift, shift_expr_code


SAMPLE = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hello")
        title.to_edge(UP)
        self.play(Write(title))
'''


def test_shift_expr_relative_axes():
    assert shift_expr_code(0.5, -0.25) == "RIGHT * 0.5 + DOWN * 0.25"
    assert shift_expr_code(-1, 0) == "LEFT * 1"


def test_propose_insert_shift():
    prop = propose_shift(
        SAMPLE, path="demo.py", name="title", dx=0.5, dy=-0.25, anchor_line=6
    )
    assert prop.ok, prop.error
    assert "title.shift(RIGHT * 0.5 + DOWN * 0.25)" in prop.proposed
    assert "title.to_edge(UP)" in prop.proposed
    assert prop.diff


def test_propose_stacks_additional_shift():
    source = SAMPLE.replace(
        "        title.to_edge(UP)\n",
        "        title.to_edge(UP)\n        title.shift(RIGHT * 0.1)\n",
    )
    prop = propose_shift(
        source, path="demo.py", name="title", dx=0.75, dy=0.0, anchor_line=6
    )
    assert prop.ok, prop.error
    assert prop.summary.startswith("insert")
    assert "title.shift(RIGHT * 0.1)" in prop.proposed
    assert "title.shift(RIGHT * 0.75)" in prop.proposed


def test_unknown_name_fails():
    prop = propose_shift(SAMPLE, path="demo.py", name="missing", dx=1, dy=0)
    assert not prop.ok

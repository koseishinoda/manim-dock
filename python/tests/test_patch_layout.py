from manim_dock.patch_layout import (
    propose_buff,
    propose_scale,
    propose_shift,
    shift_expr_code,
)


SAMPLE = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hello")
        title.to_edge(UP)
        self.play(Write(title))
'''

ARRANGE_SAMPLE = '''
from manim import *

class Demo(Scene):
    def construct(self):
        card = VGroup(Text("A"), Text("B")).arrange(DOWN, buff=0.25)
        box = SurroundingRectangle(card, buff=0.2)
        label = Text("x").next_to(card, DOWN, buff=0.15)
'''

ARRANGE_ONLY = '''
from manim import *

class Demo(Scene):
    def construct(self):
        card = VGroup(Text("A"), Text("B")).arrange(DOWN, buff=0.25)
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


def test_propose_buff_on_arrange_assignment():
    prop = propose_buff(ARRANGE_ONLY, path="demo.py", name="card", buff=0.5)
    assert prop.ok, prop.error
    assert "buff=0.5" in prop.proposed
    assert "buff=0.25" not in prop.proposed
    assert "set card buff" in prop.summary
    assert prop.dx == 0.5


def test_propose_buff_on_surrounding_rectangle():
    # Latest buff site for card is SurroundingRectangle(card, ...).
    prop = propose_buff(ARRANGE_SAMPLE, path="demo.py", name="card", buff=0.4)
    assert prop.ok, prop.error
    assert "SurroundingRectangle(card, buff=0.4)" in prop.proposed
    assert "arrange(DOWN, buff=0.25)" in prop.proposed


def test_propose_buff_on_next_to_expr():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hi")
        title.next_to(Dot(), DOWN, buff=0.1)
'''
    prop = propose_buff(source, path="demo.py", name="title", buff=0.35)
    assert prop.ok, prop.error
    assert "buff=0.35" in prop.proposed


def test_propose_buff_inserts_when_missing():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        group = VGroup(Dot(), Dot()).arrange(DOWN)
'''
    prop = propose_buff(source, path="demo.py", name="group", buff=0.3)
    assert prop.ok, prop.error
    assert "buff=0.3" in prop.proposed


def test_propose_buff_no_site_fails():
    prop = propose_buff(SAMPLE, path="demo.py", name="title", buff=0.5)
    assert not prop.ok
    assert "no editable buff site" in (prop.error or "")


def test_propose_scale_insert():
    prop = propose_scale(
        SAMPLE, path="demo.py", name="title", factor=1.5, anchor_line=6
    )
    assert prop.ok, prop.error
    assert "title.scale(1.5)" in prop.proposed
    assert "title.to_edge(UP)" in prop.proposed
    assert prop.summary.startswith("insert")


def test_propose_scale_rejects_one_and_nonpositive():
    assert not propose_scale(SAMPLE, path="demo.py", name="title", factor=1.0).ok
    assert not propose_scale(SAMPLE, path="demo.py", name="title", factor=0.0).ok
    assert not propose_scale(SAMPLE, path="demo.py", name="title", factor=-2.0).ok

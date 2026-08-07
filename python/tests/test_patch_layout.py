from manim_dock.patch_layout import (
    propose_buff,
    propose_font_size,
    propose_lag_ratio,
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


def test_propose_coalesces_additional_shift():
    source = SAMPLE.replace(
        "        title.to_edge(UP)\n",
        "        title.to_edge(UP)\n        title.shift(RIGHT * 0.1)\n",
    )
    prop = propose_shift(
        source, path="demo.py", name="title", dx=0.75, dy=0.0, anchor_line=6
    )
    assert prop.ok, prop.error
    assert prop.summary.startswith("coalesce")
    assert "title.shift(RIGHT * 0.85)" in prop.proposed
    assert "title.shift(RIGHT * 0.1)" not in prop.proposed
    assert prop.proposed.count("title.shift(") == 1


def test_propose_coalesces_stacked_shifts():
    source = SAMPLE.replace(
        "        title.to_edge(UP)\n",
        "        title.to_edge(UP)\n"
        "        title.shift(LEFT * 6.6111)\n"
        "        title.shift(RIGHT * 0.2478 + DOWN * 3.5929)\n",
    )
    prop = propose_shift(
        source, path="demo.py", name="title", dx=0.1239, dy=1.0841, anchor_line=6
    )
    assert prop.ok, prop.error
    assert prop.proposed.count("title.shift(") == 1
    assert "title.shift(LEFT * 6.2394 + DOWN * 2.5088)" in prop.proposed


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


FONT_SIZE_SAMPLE = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hello", font_size=40)
        title.to_edge(UP)
'''

LAGGED_SAMPLE = '''
from manim import *

class Demo(Scene):
    def construct(self):
        steps = VGroup(Text("1"), Text("2")).arrange(DOWN)
        self.play(LaggedStart(*[FadeIn(s, shift=RIGHT * 0.2) for s in steps], lag_ratio=0.35))
'''


def test_propose_font_size_updates_literal():
    prop = propose_font_size(
        FONT_SIZE_SAMPLE, path="demo.py", name="title", font_size=48
    )
    assert prop.ok, prop.error
    assert "font_size=48" in prop.proposed
    assert "font_size=40" not in prop.proposed
    assert "set title font_size" in prop.summary


def test_propose_font_size_inserts_when_missing():
    prop = propose_font_size(SAMPLE, path="demo.py", name="title", font_size=36)
    assert prop.ok, prop.error
    assert "font_size=36" in prop.proposed
    assert 'Text("Hello"' in prop.proposed


def test_propose_font_size_on_mathtex():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        eq = MathTex("a^2", font_size=40)
'''
    prop = propose_font_size(source, path="demo.py", name="eq", font_size=56)
    assert prop.ok, prop.error
    assert "font_size=56" in prop.proposed


def test_propose_font_size_chained_ctor():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hi", font_size=40).to_edge(UP)
'''
    prop = propose_font_size(source, path="demo.py", name="title", font_size=28)
    assert prop.ok, prop.error
    assert "font_size=28" in prop.proposed
    assert ".to_edge(UP)" in prop.proposed


def test_propose_lag_ratio_updates_literal():
    prop = propose_lag_ratio(
        LAGGED_SAMPLE, path="demo.py", name="steps", lag_ratio=0.5
    )
    assert prop.ok, prop.error
    assert "lag_ratio=0.5" in prop.proposed
    assert "lag_ratio=0.35" not in prop.proposed
    assert "set steps lag_ratio" in prop.summary


def test_propose_lag_ratio_inserts_when_missing():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        steps = VGroup(Text("1"), Text("2"))
        self.play(LaggedStart(*[FadeIn(s) for s in steps]))
'''
    prop = propose_lag_ratio(source, path="demo.py", name="steps", lag_ratio=0.2)
    assert prop.ok, prop.error
    assert "lag_ratio=0.2" in prop.proposed


def test_propose_lag_ratio_no_site_fails():
    prop = propose_lag_ratio(SAMPLE, path="demo.py", name="title", lag_ratio=0.2)
    assert not prop.ok
    assert "no LaggedStart" in (prop.error or "")

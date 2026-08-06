from manim_dock.patch_timing import propose_reorder

SAMPLE = """
from manim import *

class Demo(Scene):
    def construct(self):
        self.play(FadeIn(Dot()), run_time=1.2)
        self.wait(0.5)
        self.play(FadeOut(Dot()))
"""

WITH_LOGIC = """
from manim import *

class Demo(Scene):
    def construct(self):
        self.play(FadeIn(Dot()))
        x = 1
        self.wait(0.5)
"""


def test_reorder_adjacent_play_wait():
    prop = propose_reorder(SAMPLE, path="demo.py", line_a=6, line_b=7)
    assert prop.ok, prop.error
    construct = prop.proposed
    wait_idx = construct.index("self.wait(0.5)")
    play_idx = construct.index("self.play(FadeIn(Dot()), run_time=1.2)")
    assert wait_idx < play_idx
    assert "self.play(FadeOut(Dot()))" in construct
    assert prop.diff


def test_reorder_order_independent():
    a = propose_reorder(SAMPLE, path="demo.py", line_a=7, line_b=6)
    b = propose_reorder(SAMPLE, path="demo.py", line_a=6, line_b=7)
    assert a.ok and b.ok
    assert a.proposed == b.proposed


def test_reorder_refuses_intervening_logic():
    prop = propose_reorder(WITH_LOGIC, path="demo.py", line_a=6, line_b=8)
    assert not prop.ok
    assert prop.error
    assert "adjacent" in prop.error or "intervening" in prop.error

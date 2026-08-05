from manim_dock.patch_timing import propose_duration

SAMPLE = """
from manim import *

class Demo(Scene):
    def construct(self):
        self.play(FadeIn(Dot()), run_time=1.2)
        self.wait(0.5)
        self.play(FadeOut(Dot()))
"""


def test_patch_wait_literal():
    prop = propose_duration(
        SAMPLE, path="demo.py", kind="wait", line=7, duration=0.8
    )
    assert prop.ok, prop.error
    assert "self.wait(0.8)" in prop.proposed
    assert "self.wait(0.5)" not in prop.proposed


def test_patch_play_run_time():
    prop = propose_duration(
        SAMPLE, path="demo.py", kind="play", line=6, duration=2.0
    )
    assert prop.ok, prop.error
    assert "run_time=2" in prop.proposed


def test_insert_run_time_when_missing():
    prop = propose_duration(
        SAMPLE, path="demo.py", kind="play", line=8, duration=0.4
    )
    assert prop.ok, prop.error
    assert "run_time=0.4" in prop.proposed

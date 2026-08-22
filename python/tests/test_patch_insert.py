from manim_dock.patch_insert import propose_insert_play, propose_insert_wait

SAMPLE = """
from manim import *

class Demo(Scene):
    def construct(self):
        self.play(FadeIn(Dot()), run_time=1.2)
        self.wait(0.5)
        self.next_section("part_b")
        title = Text("Hi")
"""


def test_insert_wait_after_play():
    prop = propose_insert_wait(SAMPLE, path="demo.py", after_line=6, duration=0.5)
    assert prop.ok, prop.error
    assert "self.wait(0.5)" in prop.proposed
    lines = prop.proposed.splitlines()
    # Original wait stays; new wait appears after the play line.
    play_idx = next(i for i, ln in enumerate(lines) if "self.play(FadeIn" in ln)
    assert "self.wait(0.5)" in lines[play_idx + 1]
    assert prop.summary.startswith("insert self.wait(0.5)")


def test_insert_wait_custom_duration():
    prop = propose_insert_wait(SAMPLE, path="demo.py", after_line=7, duration=1.25)
    assert prop.ok, prop.error
    assert "self.wait(1.25)" in prop.proposed


def test_insert_play_after_wait():
    prop = propose_insert_play(
        SAMPLE, path="demo.py", after_line=7, anim_code="FadeOut(Dot())"
    )
    assert prop.ok, prop.error
    assert "self.play(FadeOut(Dot()))" in prop.proposed
    lines = prop.proposed.splitlines()
    wait_idx = next(i for i, ln in enumerate(lines) if ln.strip() == "self.wait(0.5)")
    assert "self.play(FadeOut(Dot()))" in lines[wait_idx + 1]


def test_insert_play_default_scaffold():
    prop = propose_insert_play(SAMPLE, path="demo.py", after_line=6)
    assert prop.ok, prop.error
    assert "self.play(FadeIn(Dot()))" in prop.proposed


def test_insert_after_next_section():
    prop = propose_insert_wait(SAMPLE, path="demo.py", after_line=8, duration=0.3)
    assert prop.ok, prop.error
    assert "self.wait(0.3)" in prop.proposed
    lines = prop.proposed.splitlines()
    sec_idx = next(i for i, ln in enumerate(lines) if "next_section" in ln)
    assert "self.wait(0.3)" in lines[sec_idx + 1]


def test_insert_after_non_preferred_still_ok():
    prop = propose_insert_wait(SAMPLE, path="demo.py", after_line=9, duration=0.2)
    assert prop.ok, prop.error
    assert "anchor is not play/wait/next_section" in prop.summary
    assert "self.wait(0.2)" in prop.proposed


def test_insert_rejects_bad_line():
    prop = propose_insert_wait(SAMPLE, path="demo.py", after_line=2, duration=0.5)
    assert not prop.ok
    assert "function body" in (prop.error or "")


def test_insert_rejects_negative_duration():
    prop = propose_insert_wait(SAMPLE, path="demo.py", after_line=6, duration=-1)
    assert not prop.ok


def test_insert_rejects_bad_anim_code():
    prop = propose_insert_play(
        SAMPLE, path="demo.py", after_line=6, anim_code="FadeIn("
    )
    assert not prop.ok
    assert "anim_code" in (prop.error or "").lower() or "invalid" in (
        prop.error or ""
    ).lower()

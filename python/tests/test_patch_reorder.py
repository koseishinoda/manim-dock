from manim_dock.patch_timing import (
    propose_reorder,
    propose_section_reorder,
    same_section,
)
from manim_dock.timeline import parse_scene_timeline

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

SECTIONS = """
from manim import *

class Demo(Scene):
    def construct(self):
        self.next_section("Title")
        self.title_card()

        self.next_section("Definition")
        self.definition_block()

        self.next_section("Steps")
        self.step_list()

    def title_card(self):
        self.play(FadeIn(Dot()), run_time=1.2)
        self.wait(0.5)

    def definition_block(self):
        self.play(FadeIn(Text("def")))
        self.wait(0.3)

    def step_list(self):
        self.play(FadeIn(Text("steps")))
"""

CROSS_SECTION = """
from manim import *

class Demo(Scene):
    def construct(self):
        self.next_section("A")
        self.play(FadeIn(Dot()))
        self.next_section("B")
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


def test_reorder_play_wait_same_method_still_works():
    """play/wait within one helper (or construct) remain reorderable when adjacent."""
    # title_card: play @ L16, wait @ L17
    prop = propose_reorder(SECTIONS, path="demo.py", line_a=16, line_b=17)
    assert prop.ok, prop.error
    # title_card body: wait should precede the FadeIn play after swap
    title = prop.proposed
    start = title.index("def title_card")
    end = title.index("def definition_block")
    body = title[start:end]
    assert body.index("self.wait(0.5)") < body.index(
        "self.play(FadeIn(Dot()), run_time=1.2)"
    )


def test_section_block_swap_adjacent():
    # Title @ L6, Definition @ L9
    prop = propose_section_reorder(SECTIONS, path="demo.py", line_a=6, line_b=9)
    assert prop.ok, prop.error
    construct_start = prop.proposed.index("def construct")
    construct_end = prop.proposed.index("def title_card")
    construct = prop.proposed[construct_start:construct_end]
    def_idx = construct.index('self.next_section("Definition")')
    title_idx = construct.index('self.next_section("Title")')
    steps_idx = construct.index('self.next_section("Steps")')
    assert def_idx < title_idx < steps_idx
    # Method calls travel with their section markers
    assert construct.index("self.definition_block()") < construct.index(
        "self.title_card()"
    )
    assert "swap section" in prop.summary


def test_section_block_swap_order_independent():
    a = propose_section_reorder(SECTIONS, path="demo.py", line_a=9, line_b=6)
    b = propose_section_reorder(SECTIONS, path="demo.py", line_a=6, line_b=9)
    assert a.ok and b.ok, (a.error, b.error)
    assert a.proposed == b.proposed


def test_section_reorder_refuses_non_adjacent():
    # Title @ L6 and Steps @ L12 — Definition lies between
    prop = propose_section_reorder(SECTIONS, path="demo.py", line_a=6, line_b=12)
    assert not prop.ok
    assert prop.error
    assert "adjacent" in prop.error


def test_section_reorder_refuses_play_lines():
    prop = propose_section_reorder(SAMPLE, path="demo.py", line_a=6, line_b=7)
    assert not prop.ok


def test_timeline_stamps_section_on_events():
    tl = parse_scene_timeline(SECTIONS, "<mem>", "Demo")
    assert not tl.errors
    sections = {e.label: e for e in tl.events if e.kind == "next_section"}
    assert sections["Title"].section == "Title"
    plays = [e for e in tl.events if e.kind == "play"]
    assert plays[0].section == "Title"
    assert plays[1].section == "Definition"
    assert same_section(plays[0].section, "Title")
    assert not same_section(plays[0].section, plays[1].section)


def test_same_section_helper():
    assert same_section("A", "A")
    assert same_section("", "")
    assert same_section(None, "")
    assert not same_section("A", "B")


def test_cross_section_play_wait_not_adjacent_in_ast():
    """play in A and wait in B are separated by next_section — propose_reorder refuses."""
    prop = propose_reorder(CROSS_SECTION, path="demo.py", line_a=7, line_b=9)
    assert not prop.ok

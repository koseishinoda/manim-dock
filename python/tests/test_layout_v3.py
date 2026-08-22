"""V3 Phase 9 — Stage layout fidelity (ctor chains, next_to, arrange)."""

from manim_dock.layout import FRAME_HEIGHT, EDGE_INSET, parse_scene_layout


def test_ctor_chain_to_edge_registers_and_places_near_top():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("x").to_edge(UP)
'''
    layout = parse_scene_layout(source, "<mem>", "Demo")
    assert not layout.errors
    title = next(i for i in layout.items if i.name == "title")
    assert title.mobject_kind == "Text"
    assert any(c.kind == "to_edge" for c in title.layout_calls)
    expected_y = FRAME_HEIGHT / 2.0 - EDGE_INSET
    assert abs(title.y - expected_y) < 1e-9
    assert abs(title.x) < 1e-9


def test_separate_to_edge_then_shift_still_works():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hello")
        title.to_edge(UP)
        title.shift(LEFT)
'''
    layout = parse_scene_layout(source, "<mem>", "Demo")
    title = next(i for i in layout.items if i.name == "title")
    assert title.y > 2.0
    assert title.x == -1.0


def test_next_to_after_both_assigned():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        b = Text("b").to_edge(UP)
        a = Text("a")
        a.next_to(b, DOWN, buff=0.3)
'''
    layout = parse_scene_layout(source, "<mem>", "Demo")
    a = next(i for i in layout.items if i.name == "a")
    b = next(i for i in layout.items if i.name == "b")
    assert b.y > 2.0
    # Approximate: a ≈ b + unit(DOWN) * (1 + 0.3)
    assert a.y < b.y
    assert abs(a.x - b.x) < 1e-9
    assert abs(a.y - (b.y - 1.3)) < 1e-9


def test_arrange_spreads_named_children():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        a = Text("a")
        b = Text("b")
        group = VGroup(a, b).arrange(DOWN, buff=0.25)
'''
    layout = parse_scene_layout(source, "<mem>", "Demo")
    a = next(i for i in layout.items if i.name == "a")
    b = next(i for i in layout.items if i.name == "b")
    group = next(i for i in layout.items if i.name == "group")
    assert group.mobject_kind == "VGroup"
    assert any(c.kind == "arrange" for c in group.layout_calls)
    # Centered on group origin; step = 1.25 along DOWN
    assert a.y > b.y
    assert abs(a.y - 0.625) < 1e-9
    assert abs(b.y - (-0.625)) < 1e-9

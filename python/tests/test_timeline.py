from manim_dock.timeline import parse_scene_timeline

from fixtures import LESSON_SOURCE


def test_lesson_timeline_expands_helpers():
    tl = parse_scene_timeline(LESSON_SOURCE, "<fixture>", "MinimalLesson")
    assert not tl.errors
    kinds = [e.kind for e in tl.events]
    assert kinds.count("next_section") >= 5
    assert "play" in kinds
    assert "wait" in kinds
    assert tl.total_duration > 0

    # First play is Write(title) with literal run_time
    plays = [e for e in tl.events if e.kind == "play"]
    assert plays
    assert plays[0].editable
    assert abs(plays[0].duration - 1.2) < 1e-9
    assert plays[0].targets == ["title"]
    assert plays[0].label == "Write title"


def test_constant_wait_not_editable():
    tl = parse_scene_timeline(LESSON_SOURCE, "<fixture>", "MinimalLesson")
    waits = [e for e in tl.events if e.kind == "wait" and "DEFAULT_WAIT" in e.label]
    assert waits
    assert all(not w.editable for w in waits)
    assert all(w.duration_source == "constant" for w in waits)


def test_implicit_run_time_editable():
    source = """
from manim import *

class Demo(Scene):
    def construct(self):
        self.play(FadeIn(Dot()))
        self.wait(0.25)
"""
    tl = parse_scene_timeline(source, "<mem>", "Demo")
    play = next(e for e in tl.events if e.kind == "play")
    assert play.editable
    assert play.duration_source == "default"
    assert play.targets == []
    assert "FadeIn" in play.label
    wait = next(e for e in tl.events if e.kind == "wait")
    assert wait.editable
    assert abs(wait.duration - 0.25) < 1e-9


def test_play_targets_single_and_multi():
    source = """
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hi")
        sub = Text("there")
        self.play(Write(title))
        self.play(Write(title), FadeIn(sub))
        self.play(FadeOut(title), FadeOut(sub))
"""
    tl = parse_scene_timeline(source, "<mem>", "Demo")
    plays = [e for e in tl.events if e.kind == "play"]
    assert len(plays) == 3
    assert plays[0].targets == ["title"]
    assert plays[0].label == "Write title"
    assert plays[1].targets == ["title", "sub"]
    assert plays[1].label == "play Write(title), FadeIn(sub)"
    assert plays[2].targets == ["title", "sub"]
    assert "FadeOut(title)" in plays[2].label
    assert "FadeOut(sub)" in plays[2].label


def test_play_targets_attribute_and_subscript():
    source = """
from manim import *

class Demo(Scene):
    def construct(self):
        eq = MathTex("a", "b")
        self.play(Indicate(eq[0]))
        self.play(Write(self.title))
"""
    tl = parse_scene_timeline(source, "<mem>", "Demo")
    plays = [e for e in tl.events if e.kind == "play"]
    assert plays[0].targets == ["eq[0]"]
    assert plays[0].label == "Indicate eq[0]"
    assert plays[1].targets == ["title"]
    assert plays[1].label == "Write title"


def test_play_targets_lagged_start_comprehension():
    source = """
from manim import *

class Demo(Scene):
    def construct(self):
        hyp = VGroup(Text("a"), Text("b"))
        self.play(LaggedStart(*[FadeIn(x) for x in hyp], lag_ratio=0.25))
"""
    tl = parse_scene_timeline(source, "<mem>", "Demo")
    plays = [e for e in tl.events if e.kind == "play"]
    assert plays[0].targets == ["hyp"]
    assert "LaggedStart" in plays[0].label
    assert "hyp" in plays[0].label

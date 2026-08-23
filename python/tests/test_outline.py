from pathlib import Path

from manim_dock.outline import parse_file, parse_source

ROOT = Path(__file__).resolve().parents[2]
LESSON = ROOT / "examples" / "minimal_lesson" / "lesson.py"


def test_parse_minimal_lesson_scenes():
    outline = parse_file(LESSON)
    assert not outline.errors
    names = [s.name for s in outline.scenes]
    assert "MinimalLesson" in names
    scene = next(s for s in outline.scenes if s.name == "MinimalLesson")
    method_names = [m.name for m in scene.methods]
    assert "construct" in method_names
    assert "title_card" in method_names
    construct = next(m for m in scene.methods if m.name == "construct")
    kinds = [e.kind for e in construct.events]
    assert "next_section" in kinds
    assert "play" in kinds or any(
        "play" in [e.kind for e in m.events] for m in scene.methods
    )


def test_nested_vgroup_scene_still_outlines():
    source = '''
from manim import *

class Nested(Scene):
    def construct(self):
        group = VGroup(VGroup(Dot(), Dot()), Text("x"))
        self.play(FadeIn(group))
        self.wait(0.5)
'''
    outline = parse_source(source, path="<nested>")
    assert len(outline.scenes) == 1
    events = outline.scenes[0].methods[0].events
    assert [e.kind for e in events] == ["play", "wait"]
    assert events[0].targets == ["group"]
    assert events[0].label == "FadeIn group"


def test_play_outline_shows_object_names():
    source = '''
from manim import *

class Demo(Scene):
    def construct(self):
        title = Text("Hi")
        self.play(Write(title))
'''
    outline = parse_source(source, path="<play>")
    play = outline.scenes[0].methods[0].events[0]
    assert play.kind == "play"
    assert play.targets == ["title"]
    assert play.label == "Write title"


def test_syntax_error_reports_without_crash():
    outline = parse_source("class Broken(Scene):\n    def construct(self)\n", path="<bad>")
    assert outline.errors
    assert outline.scenes == []

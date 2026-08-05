from pathlib import Path

from manim_dock.timeline import parse_file_timeline, parse_scene_timeline

ROOT = Path(__file__).resolve().parents[2]
LESSON = ROOT / "examples" / "minimal_lesson" / "lesson.py"


def test_lesson_timeline_expands_helpers():
    tl = parse_file_timeline(LESSON, "MinimalLesson")
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


def test_constant_wait_not_editable():
    tl = parse_file_timeline(LESSON, "MinimalLesson")
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
    wait = next(e for e in tl.events if e.kind == "wait")
    assert wait.editable
    assert abs(wait.duration - 0.25) < 1e-9

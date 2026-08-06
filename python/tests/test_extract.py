from pathlib import Path

from manim_dock.extract import propose_extract_method

from fixtures import LESSON_SOURCE

ROOT = Path(__file__).resolve().parents[2]


def test_extract_title_card():
    prop = propose_extract_method(
        LESSON_SOURCE,
        scene_path="lesson.py",
        scene_name="MinimalLesson",
        method_name="title_card",
        library_path=str(ROOT / "examples" / "lesson_lib" / "extracted.py"),
        library_source="",
    )
    assert prop.ok, prop.error
    assert "def title_card(scene" in prop.library_proposed
    assert "scene.play" in prop.library_proposed
    assert "self.play" not in prop.library_proposed.split("def title_card", 1)[-1]
    assert "from lesson_lib.extracted import title_card" in prop.scene_proposed
    assert "title_card(self)" in prop.scene_proposed
    # Original method body should not remain.
    assert 'Text("Why does this formula work?"' not in prop.scene_proposed


def test_refuse_construct():
    prop = propose_extract_method(
        LESSON_SOURCE,
        scene_path="lesson.py",
        scene_name="MinimalLesson",
        method_name="construct",
        library_path="/tmp/x.py",
        library_source="",
    )
    assert not prop.ok


def test_refuse_already_extracted_stub():
    source = '''
from manim import *
from lesson_lib.extracted import title_card

class Demo(Scene):
    def construct(self):
        self.title_card()

    def title_card(self):
        title_card(self)
'''
    prop = propose_extract_method(
        source,
        scene_path="demo.py",
        scene_name="Demo",
        method_name="title_card",
        library_path="/tmp/out.py",
        library_source="",
    )
    assert not prop.ok
    assert "already delegates" in (prop.error or "")

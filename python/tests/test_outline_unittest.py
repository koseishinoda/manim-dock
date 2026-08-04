import unittest
from pathlib import Path

from manim_dock.outline import parse_file, parse_source

ROOT = Path(__file__).resolve().parents[2]
LESSON = ROOT / "examples" / "minimal_lesson" / "lesson.py"


class OutlineTests(unittest.TestCase):
    def test_parse_minimal_lesson_scenes(self) -> None:
        outline = parse_file(LESSON)
        self.assertEqual(outline.errors, [])
        names = [s.name for s in outline.scenes]
        self.assertIn("MinimalLesson", names)
        scene = next(s for s in outline.scenes if s.name == "MinimalLesson")
        method_names = [m.name for m in scene.methods]
        self.assertIn("construct", method_names)
        self.assertIn("title_card", method_names)
        construct = next(m for m in scene.methods if m.name == "construct")
        kinds = [e.kind for e in construct.events]
        self.assertIn("next_section", kinds)

    def test_nested_vgroup_scene_still_outlines(self) -> None:
        source = """
from manim import *

class Nested(Scene):
    def construct(self):
        group = VGroup(VGroup(Dot(), Dot()), Text("x"))
        self.play(FadeIn(group))
        self.wait(0.5)
"""
        outline = parse_source(source, path="<nested>")
        self.assertEqual(len(outline.scenes), 1)
        events = outline.scenes[0].methods[0].events
        self.assertEqual([e.kind for e in events], ["play", "wait"])

    def test_syntax_error_reports_without_crash(self) -> None:
        outline = parse_source(
            "class Broken(Scene):\n    def construct(self)\n", path="<bad>"
        )
        self.assertTrue(outline.errors)
        self.assertEqual(outline.scenes, [])


if __name__ == "__main__":
    unittest.main()

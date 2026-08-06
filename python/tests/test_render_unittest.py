import unittest
from pathlib import Path
from unittest import mock

from manim_dock.render import (
    RenderResult,
    _extract_output_path,
    _quality_flag,
    render_scene,
    resolve_manim_cmd,
)


class RenderHelperTests(unittest.TestCase):
    def test_quality_flag(self) -> None:
        self.assertEqual(_quality_flag("l"), "-ql")
        self.assertEqual(_quality_flag("low"), "-ql")
        self.assertEqual(_quality_flag("m"), "-qm")

    def test_extract_output_path(self) -> None:
        log = "Something\nFile ready at '/tmp/out/Scene.mp4'\nDone\n"
        self.assertEqual(_extract_output_path(log), "/tmp/out/Scene.mp4")

    def test_resolve_manim_cmd_falls_back_to_module(self) -> None:
        with mock.patch("manim_dock.render.shutil.which", return_value=None):
            cmd = resolve_manim_cmd("/usr/bin/python3")
        self.assertEqual(cmd, ["/usr/bin/python3", "-m", "manim"])

    def test_render_missing_file(self) -> None:
        result = render_scene("/no/such/file.py", "Scene")
        self.assertFalse(result.ok)
        self.assertIn("not found", result.error or "")

    def test_render_success_parses_file_ready(self) -> None:
        fake = Path(__file__).resolve()
        completed = mock.Mock(
            returncode=0,
            stdout="File ready at '/tmp/MinimalLesson.mp4'\n",
            stderr="",
        )
        with mock.patch("manim_dock.render.subprocess.run", return_value=completed):
            result = render_scene(fake, "MinimalLesson", quality="l")
        self.assertTrue(result.ok)
        self.assertEqual(result.output_path, "/tmp/MinimalLesson.mp4")
        self.assertIn("-ql", result.command)
        self.assertIn("MinimalLesson", result.command)

    def test_render_includes_save_sections_flag(self) -> None:
        fake = Path(__file__).resolve()
        completed = mock.Mock(
            returncode=0,
            stdout="File ready at '/tmp/MinimalLesson.mp4'\n",
            stderr="",
        )
        with mock.patch("manim_dock.render.subprocess.run", return_value=completed):
            result = render_scene(fake, "MinimalLesson", save_sections=True)
        self.assertIn("--save_sections", result.command)


if __name__ == "__main__":
    unittest.main()

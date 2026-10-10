import tempfile
import unittest
from pathlib import Path
from unittest import mock

from manim_dock.render import (
    RenderResult,
    _extract_output_path,
    _find_newest_media,
    _quality_flag,
    quality_media_dir,
    render_scene,
    render_scenes,
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

    def test_extract_output_path_rich_wrapped(self) -> None:
        # Manim rich console wraps long paths across padded lines.
        log = """
                    INFO                                scene_file_writer.py:893
                             File ready at
                             '/home/kshinoda/Workspace/
                             Manimspace/Nyquist_Stabili
                             ty_Criteria/nyquist-stabil
                             ity/media/images/theme_exa
                             mple_specific/TokyonightPr
                             eview_ManimCE_v0.19.2.png'
"""
        self.assertEqual(
            _extract_output_path(log),
            "/home/kshinoda/Workspace/Manimspace/Nyquist_Stability_Criteria/"
            "nyquist-stability/media/images/theme_example_specific/"
            "TokyonightPreview_ManimCE_v0.19.2.png",
        )

    def test_find_newest_media_does_not_pick_unrelated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "videos" / "theme_example" / "ThemeCarousel.mp4"
            other.parent.mkdir(parents=True)
            other.write_bytes(b"fake")
            # No Tokyonight media — must not return ThemeCarousel.
            self.assertIsNone(_find_newest_media(root, "TokyonightPreview"))

    def test_find_newest_media_prefers_matching_still(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            other = root / "videos" / "theme_example" / "ThemeCarousel.mp4"
            still = (
                root
                / "images"
                / "theme_example_specific"
                / "TokyonightPreview_ManimCE_v0.19.2.png"
            )
            other.parent.mkdir(parents=True)
            still.parent.mkdir(parents=True)
            other.write_bytes(b"other")
            still.write_bytes(b"still")
            self.assertEqual(
                _find_newest_media(root, "TokyonightPreview"),
                str(still.resolve()),
            )

    def test_find_newest_media_prefers_matching_video_over_still(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            still = root / "images" / "TokyonightPreview.png"
            video = root / "videos" / "TokyonightPreview.mp4"
            still.parent.mkdir(parents=True)
            video.parent.mkdir(parents=True)
            still.write_bytes(b"still")
            video.write_bytes(b"video")
            self.assertEqual(
                _find_newest_media(root, "TokyonightPreview"),
                str(video.resolve()),
            )

    def test_render_success_parses_wrapped_still(self) -> None:
        fake = Path(__file__).resolve()
        wrapped = """
                    INFO                                scene_file_writer.py:893
                             File ready at
                             '/tmp/media/images/scene/T
                             okyonightPreview_ManimCE_v
                             0.19.2.png'
"""
        completed = mock.Mock(returncode=0, stdout=wrapped, stderr="")
        with mock.patch("manim_dock.render.subprocess.run", return_value=completed):
            result = render_scene(fake, "TokyonightPreview", quality="l")
        self.assertTrue(result.ok)
        self.assertEqual(
            result.output_path,
            "/tmp/media/images/scene/TokyonightPreview_ManimCE_v0.19.2.png",
        )

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

    def test_quality_media_dir(self) -> None:
        self.assertEqual(quality_media_dir("l"), "480p15")
        self.assertEqual(quality_media_dir("m"), "720p30")
        self.assertEqual(quality_media_dir("h"), "1080p60")
        self.assertEqual(quality_media_dir("k"), "2160p60")

    def test_render_scenes_builds_multi_scene_argv(self) -> None:
        fake = Path(__file__).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "script.py"
            script.write_text("from manim import *\nclass A(Scene):\n    pass\n", encoding="utf-8")
            qdir = Path(tmp) / "media" / "videos" / "script" / "480p15"
            qdir.mkdir(parents=True)
            (qdir / "SceneA.mp4").write_bytes(b"a")
            (qdir / "SceneB.mp4").write_bytes(b"b")
            completed = mock.Mock(returncode=0, stdout="", stderr="")
            with mock.patch(
                "manim_dock.render.subprocess.run", return_value=completed
            ) as run:
                result = render_scenes(
                    script, ["SceneA", "SceneB"], quality="l"
                )
            cmd = run.call_args.args[0]
            self.assertIn("-ql", cmd)
            self.assertEqual(cmd[-2:], ["SceneA", "SceneB"])
            self.assertTrue(result.ok)
            self.assertEqual(result.quality_dir, "480p15")
            self.assertEqual(
                [o.scene for o in result.outputs], ["SceneA", "SceneB"]
            )
            self.assertTrue(all(o.path for o in result.outputs))

    def test_render_scenes_empty_names(self) -> None:
        fake = Path(__file__).resolve()
        result = render_scenes(fake, [], quality="l")
        self.assertFalse(result.ok)
        self.assertIn("no scene", result.error or "")


if __name__ == "__main__":
    unittest.main()

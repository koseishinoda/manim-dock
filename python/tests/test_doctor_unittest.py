import unittest

from manim_dock.doctor import run_doctor


class DoctorTests(unittest.TestCase):
    def test_doctor_includes_core_probes(self) -> None:
        probes = {p.name: p for p in run_doctor()}
        self.assertIn("python", probes)
        self.assertTrue(probes["python"].ok)
        self.assertIn("manim", probes)
        self.assertIn("latex", probes)
        self.assertIn("ffmpeg", probes)


if __name__ == "__main__":
    unittest.main()

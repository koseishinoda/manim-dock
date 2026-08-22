from manim_dock.doctor import run_doctor
from manim_dock.version_matrix import MANIM_CE_SUPPORTED_LABEL


def test_doctor_includes_core_probes():
    probes = {p.name: p for p in run_doctor()}
    assert "python" in probes
    assert probes["python"].ok
    assert "manim" in probes
    assert "manim_support" in probes
    assert MANIM_CE_SUPPORTED_LABEL in probes["manim_support"].detail
    assert "latex" in probes
    assert "ffmpeg" in probes
    assert "libcst" in probes

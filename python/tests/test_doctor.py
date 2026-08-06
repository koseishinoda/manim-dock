from manim_dock.doctor import run_doctor


def test_doctor_includes_core_probes():
    probes = {p.name: p for p in run_doctor()}
    assert "python" in probes
    assert probes["python"].ok
    assert "manim" in probes
    assert "latex" in probes
    assert "ffmpeg" in probes
    assert "libcst" in probes

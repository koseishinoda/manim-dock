"""Unit tests for doctor version-matrix probe (V3 Phase 11)."""

from manim_dock.doctor import Probe, _probe_manim_support, _parse_version_tuple, run_doctor
from manim_dock.version_matrix import (
    MANIM_CE_MIN,
    MANIM_CE_SUPPORTED_LABEL,
    MANIM_CE_VERIFIED,
)


def test_version_matrix_constants_match_doc_intent():
    assert MANIM_CE_MIN == "0.18"
    assert "0.18" in MANIM_CE_SUPPORTED_LABEL
    assert MANIM_CE_VERIFIED == "0.20.1"


def test_parse_version_tuple_from_manim_output():
    assert _parse_version_tuple("Manim Community v0.20.1") == (0, 20, 1)
    assert _parse_version_tuple("0.18.0") == (0, 18, 0)
    assert _parse_version_tuple("no version here") is None


def test_probe_manim_support_ok_when_above_min():
    manim = Probe("manim", True, "Manim Community v0.20.1 (/usr/bin/python -m manim)")
    probe = _probe_manim_support(manim)
    assert probe.name == "manim_support"
    assert probe.ok
    assert MANIM_CE_SUPPORTED_LABEL in probe.detail
    assert MANIM_CE_MIN in probe.detail
    assert "detected: 0.20.1" in probe.detail


def test_probe_manim_support_fails_when_below_min():
    manim = Probe("manim", True, "Manim Community v0.17.3 (/usr/bin/python -m manim)")
    probe = _probe_manim_support(manim)
    assert not probe.ok
    assert "detected: 0.17.3" in probe.detail
    assert f"below minimum {MANIM_CE_MIN}" in probe.detail


def test_probe_manim_support_fails_when_missing():
    manim = Probe("manim", False, "not installed")
    probe = _probe_manim_support(manim)
    assert not probe.ok
    assert "detected: none" in probe.detail
    assert MANIM_CE_SUPPORTED_LABEL in probe.detail


def test_doctor_includes_manim_support_probe():
    probes = {p.name: p for p in run_doctor()}
    assert "manim_support" in probes
    assert MANIM_CE_SUPPORTED_LABEL in probes["manim_support"].detail
    assert "detected:" in probes["manim_support"].detail

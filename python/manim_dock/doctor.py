"""Environment probes for Manim Dock (G3)."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Any

from manim_dock.version_matrix import (
    MANIM_CE_MIN,
    MANIM_CE_SUPPORTED_LABEL,
    MANIM_CE_VERIFIED,
)


@dataclass
class Probe:
    name: str
    ok: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _run_version(cmd: list[str]) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError:
        return False, "not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    out = (proc.stdout or proc.stderr or "").strip().splitlines()
    detail = out[0] if out else f"exit {proc.returncode}"
    return proc.returncode == 0, detail


def _parse_version_tuple(text: str) -> tuple[int, ...] | None:
    """Extract a dotted version tuple from manim --version style output."""
    match = re.search(r"(\d+(?:\.\d+)+)", text)
    if not match:
        return None
    try:
        return tuple(int(part) for part in match.group(1).split("."))
    except ValueError:
        return None


def _version_meets_min(detected: tuple[int, ...], minimum: str) -> bool:
    min_tuple = tuple(int(part) for part in minimum.split("."))
    # Compare equal-length prefixes; trailing zeros on the shorter side.
    width = max(len(detected), len(min_tuple))
    left = detected + (0,) * (width - len(detected))
    right = min_tuple + (0,) * (width - len(min_tuple))
    return left >= right


def _probe_manim() -> Probe:
    """Prefer ``python -m manim`` in this interpreter; fall back to PATH script."""
    module_cmd = [sys.executable, "-m", "manim", "--version"]
    ok, detail = _run_version(module_cmd)
    if ok:
        return Probe("manim", True, f"{detail} ({sys.executable} -m manim)")

    manim_bin = shutil.which("manim")
    if manim_bin:
        ok_bin, detail_bin = _run_version([manim_bin, "--version"])
        if ok_bin:
            return Probe("manim", True, f"{detail_bin} ({manim_bin})")
        return Probe(
            "manim",
            False,
            f"manim on PATH failed ({detail_bin}); also: {sys.executable} -m manim → {detail}",
        )

    return Probe(
        "manim",
        False,
        f"not installed in {sys.executable} — "
        f"pip install manim  (or set manimDock.pythonPath to a venv that has ManimCE)",
    )


def _probe_manim_support(manim: Probe) -> Probe:
    """Report declared ManimCE support range + detected version (version-matrix)."""
    declared = (
        f"supported {MANIM_CE_SUPPORTED_LABEL} "
        f"(min {MANIM_CE_MIN}, verified {MANIM_CE_VERIFIED})"
    )
    if not manim.ok:
        return Probe(
            "manim_support",
            False,
            f"{declared}; detected: none — {manim.detail}",
        )

    parsed = _parse_version_tuple(manim.detail)
    if parsed is None:
        return Probe(
            "manim_support",
            True,
            f"{declared}; detected: {manim.detail} (could not parse version)",
        )

    detected_label = ".".join(str(part) for part in parsed)
    if _version_meets_min(parsed, MANIM_CE_MIN):
        return Probe(
            "manim_support",
            True,
            f"{declared}; detected: {detected_label}",
        )
    return Probe(
        "manim_support",
        False,
        f"{declared}; detected: {detected_label} — below minimum {MANIM_CE_MIN}",
    )


def run_doctor() -> list[Probe]:
    manim = _probe_manim()
    probes: list[Probe] = [
        Probe("python", True, f"{sys.version.split()[0]} ({sys.executable})"),
        manim,
        _probe_manim_support(manim),
    ]

    latex = shutil.which("latex") or shutil.which("pdflatex") or shutil.which("xelatex")
    probes.append(
        Probe(
            "latex",
            latex is not None,
            latex or "no latex/pdflatex/xelatex on PATH (needed for MathTex/Tex)",
        )
    )

    ffmpeg = shutil.which("ffmpeg")
    probes.append(
        Probe(
            "ffmpeg",
            ffmpeg is not None,
            ffmpeg or "ffmpeg not on PATH",
        )
    )

    try:
        import libcst  # noqa: F401

        probes.append(Probe("libcst", True, getattr(libcst, "__version__", "installed")))
    except ImportError:
        probes.append(
            Probe(
                "libcst",
                False,
                "libcst not installed — Stage/Timeline/extract patches need: pip install libcst",
            )
        )

    return probes

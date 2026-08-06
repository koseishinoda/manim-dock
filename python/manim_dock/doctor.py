"""Environment probes for Manim Dock (G3)."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import Any


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


def run_doctor() -> list[Probe]:
    probes: list[Probe] = [
        Probe("python", True, f"{sys.version.split()[0]} ({sys.executable})"),
        _probe_manim(),
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

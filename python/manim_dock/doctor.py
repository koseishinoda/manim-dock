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
            timeout=15,
            check=False,
        )
    except FileNotFoundError:
        return False, "not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "timed out"
    out = (proc.stdout or proc.stderr or "").strip().splitlines()
    detail = out[0] if out else f"exit {proc.returncode}"
    return proc.returncode == 0, detail


def run_doctor() -> list[Probe]:
    probes: list[Probe] = [
        Probe("python", True, sys.version.split()[0]),
    ]

    manim = shutil.which("manim")
    if manim is None:
        probes.append(
            Probe(
                "manim",
                False,
                "manim not on PATH — install ManimCE in the active environment",
            )
        )
    else:
        ok, detail = _run_version([manim, "--version"])
        probes.append(Probe("manim", ok, detail if ok else f"{detail} ({manim})"))

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

    return probes

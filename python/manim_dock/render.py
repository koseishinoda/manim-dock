"""Run ManimCE low-quality renders and locate the output media file."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


FILE_READY_RE = re.compile(
    r"File ready at ['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)


@dataclass
class RenderResult:
    ok: bool
    output_path: str | None = None
    command: list[str] = field(default_factory=list)
    cwd: str = ""
    returncode: int | None = None
    log_tail: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_manim_cmd(python_executable: str | None = None) -> list[str]:
    """Prefer ``manim`` on PATH, else ``python -m manim``."""
    manim = shutil.which("manim")
    if manim:
        return [manim]
    py = python_executable or sys.executable
    return [py, "-m", "manim"]


def _quality_flag(quality: str) -> str:
    q = (quality or "l").strip().lower()
    mapping = {
        "l": "l",
        "low": "l",
        "ql": "l",
        "m": "m",
        "medium": "m",
        "h": "h",
        "high": "h",
        "k": "k",
        "4k": "k",
    }
    letter = mapping.get(q, "l")
    return f"-q{letter}"


def _extract_output_path(log: str) -> str | None:
    matches = FILE_READY_RE.findall(log)
    if matches:
        return matches[-1]
    return None


def _find_newest_mp4(media_root: Path, scene_name: str) -> str | None:
    if not media_root.is_dir():
        return None
    candidates = sorted(
        media_root.rglob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    scene_lower = scene_name.lower()
    for path in candidates:
        if scene_lower in path.stem.lower():
            return str(path.resolve())
    return str(candidates[0].resolve()) if candidates else None


def render_scene(
    file_path: str | Path,
    scene_name: str,
    *,
    quality: str = "l",
    manim_cmd: list[str] | None = None,
    preview: bool = False,
    timeout: int | None = 600,
) -> RenderResult:
    path = Path(file_path).resolve()
    if not path.is_file():
        return RenderResult(ok=False, error=f"file not found: {path}")

    cwd = path.parent
    cmd = list(manim_cmd or resolve_manim_cmd())
    # Classic ManimCE CLI form (widely compatible). No `-p`: Dock shows the video.
    cmd.extend(
        [
            _quality_flag(quality),
            str(path),
            scene_name,
        ]
    )
    _ = preview  # reserved for optional external player later

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return RenderResult(
            ok=False,
            command=cmd,
            cwd=str(cwd),
            error="manim executable not found — install ManimCE or set PATH",
        )
    except subprocess.TimeoutExpired:
        return RenderResult(
            ok=False,
            command=cmd,
            cwd=str(cwd),
            error=f"render timed out after {timeout}s",
        )

    log = "\n".join(
        part for part in (proc.stdout or "", proc.stderr or "") if part
    ).strip()
    log_tail = log[-4000:] if len(log) > 4000 else log

    output = _extract_output_path(log)
    if output is None:
        output = _find_newest_mp4(cwd / "media", scene_name)

    ok = proc.returncode == 0 and bool(output)
    error = None
    if proc.returncode != 0:
        error = f"manim exited with code {proc.returncode}"
    elif not output:
        error = "render finished but output video was not found"

    return RenderResult(
        ok=ok,
        output_path=output,
        command=cmd,
        cwd=str(cwd),
        returncode=proc.returncode,
        log_tail=log_tail,
        error=error,
    )

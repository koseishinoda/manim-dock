"""Copy the minimal lesson example into a destination directory."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def _example_root() -> Path:
    # python/manim_dock/scaffold.py → repo root → examples/minimal_lesson
    return Path(__file__).resolve().parents[2] / "examples" / "minimal_lesson"


def scaffold_example(dest_dir: Path | str) -> dict[str, Any]:
    """Copy ``examples/minimal_lesson/lesson.py`` (+ README if present) into ``dest_dir``.

    Creates ``dest_dir`` if needed. Does not overwrite existing files.
    """
    dest = Path(dest_dir)
    src_root = _example_root()
    if not src_root.is_dir():
        return {
            "ok": False,
            "error": f"example not found: {src_root}",
            "dest": str(dest),
            "copied": [],
        }

    dest.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    skipped: list[str] = []

    for name in ("lesson.py", "README.md"):
        src = src_root / name
        if not src.is_file():
            continue
        target = dest / name
        if target.exists():
            skipped.append(name)
            continue
        shutil.copy2(src, target)
        copied.append(name)

    if not copied and not skipped:
        return {
            "ok": False,
            "error": "no example files to copy",
            "dest": str(dest.resolve()),
            "copied": [],
        }

    return {
        "ok": True,
        "dest": str(dest.resolve()),
        "copied": copied,
        "skipped": skipped,
        "source": str(src_root),
    }

"""ManimCE still capture for Stage at a source line (Phase 12).

Uses a temp sibling file + ``raise EndSceneEarlyException`` after the until-line
statement, then ``manim -ql -s`` (save last frame). Does not rewrite the user's
on-disk scene. Uninstall-safe — no plugin Scene base class.

Intentionally does **not** import ``manim_dock.render`` (libcst): still capture
only needs stdlib + a Manim-capable interpreter (``python -m manim``).
"""

from __future__ import annotations

import ast
import hashlib
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = "v2"
DEFAULT_TIMEOUT = 60
EARLY_EXIT_IMPORT = "from manim.utils.exceptions import EndSceneEarlyException"


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


def _write_temp_render_source(
    cwd: Path, path: Path, transformed: str, *, prefix_tag: str
) -> Path:
    """Write a hidden temp sibling file so imports resolve; return its path."""
    fd, tmp_name = tempfile.mkstemp(
        suffix=path.suffix or ".py",
        prefix=f".{path.stem}_{prefix_tag}_",
        dir=str(cwd),
    )
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            handle.write(transformed)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return Path(tmp_name)


@dataclass
class SnapshotResult:
    ok: bool
    path: str = ""
    scene: str = ""
    active_until_line: int = 0
    quality: str = "l"
    cache_key: str = ""
    cached: bool = False
    png_path: str | None = None
    width: int | None = None
    height: int | None = None
    command: list[str] = field(default_factory=list)
    returncode: int | None = None
    log_tail: str = ""
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def snapshot_cache_key(
    source: str,
    scene_name: str,
    active_until_line: int,
    *,
    quality: str = "l",
) -> str:
    payload = "\0".join(
        [
            source,
            scene_name,
            str(active_until_line),
            (quality or "l").strip().lower(),
            SNAPSHOT_VERSION,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _default_cache_dir() -> Path:
    return Path(tempfile.gettempdir()) / "manim_dock_snapshots"


def _png_size(png_path: Path) -> tuple[int | None, int | None]:
    """Read IHDR width/height without depending on Pillow."""
    try:
        data = png_path.read_bytes()
    except OSError:
        return None, None
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    # IHDR: length(4) + type(4) + width(4) + height(4)
    width = int.from_bytes(data[16:20], "big")
    height = int.from_bytes(data[20:24], "big")
    return width, height


def _find_newest_png(media_root: Path, scene_name: str) -> str | None:
    if not media_root.is_dir():
        return None
    candidates = sorted(
        media_root.rglob("*.png"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    scene_lower = scene_name.lower()
    for path in candidates:
        if scene_lower in path.stem.lower():
            return str(path.resolve())
    return str(candidates[0].resolve()) if candidates else None


def _extract_png_path(log: str) -> str | None:
    import re

    matches = re.findall(
        r"File ready at ['\"]([^'\"]+\.png)['\"]",
        log,
        flags=re.IGNORECASE,
    )
    if matches:
        return matches[-1]
    # Broader: any File ready path ending in .png
    for m in re.findall(r"File ready at ['\"]([^'\"]+)['\"]", log, flags=re.IGNORECASE):
        if m.lower().endswith(".png"):
            return m
    return None


def _ensure_early_exit_import(tree: ast.Module) -> None:
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            try:
                text = ast.unparse(node)
            except Exception:
                continue
            if "EndSceneEarlyException" in text:
                return

    # Must stay after module docstring + ``from __future__`` (SyntaxError otherwise).
    insert_at = 0
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(
        getattr(body[0], "value", None), ast.Constant
    ):
        insert_at = 1
    while insert_at < len(body):
        node = body[insert_at]
        if isinstance(node, ast.ImportFrom) and node.module == "__future__":
            insert_at += 1
            continue
        break
    body.insert(insert_at, ast.parse(EARLY_EXIT_IMPORT).body[0])


def _stmt_end_line(node: ast.AST) -> int:
    return int(getattr(node, "end_lineno", None) or getattr(node, "lineno", 0) or 0)


def _is_construct(node: ast.AST) -> bool:
    return (
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "construct"
    )


def _find_construct(
    tree: ast.Module, until_line: int, scene_name: str | None = None
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Locate ``construct`` for the scene class that owns ``until_line``."""
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]

    def construct_of(
        cls: ast.ClassDef,
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        for item in cls.body:
            if _is_construct(item):
                return item
        return None

    containing = [
        cls
        for cls in classes
        if cls.lineno <= until_line <= _stmt_end_line(cls)
    ]

    if scene_name:
        for cls in containing:
            if cls.name == scene_name:
                found = construct_of(cls)
                if found is not None:
                    return found
        for cls in classes:
            if cls.name == scene_name:
                found = construct_of(cls)
                if found is not None:
                    return found

    if containing:
        found = construct_of(containing[-1])
        if found is not None:
            return found

    for cls in classes:
        found = construct_of(cls)
        if found is not None:
            return found
    return None


def _find_anchor_in_construct(
    construct: ast.FunctionDef | ast.AsyncFunctionDef, until_line: int
) -> tuple[list[ast.stmt], int] | None:
    """Last statement inside ``construct`` with ``end_lineno <= until_line``.

    Never anchors on nested ``ClassDef`` / ``FunctionDef`` — only executable
    statements whose raise can run during ``construct()``.
    """
    best: tuple[list[ast.stmt], int, int] | None = None  # body, idx, end

    def consider(body: list[ast.stmt]) -> None:
        nonlocal best
        for i, stmt in enumerate(body):
            if isinstance(
                stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            end = _stmt_end_line(stmt)
            if end <= 0 or end > until_line:
                continue
            if best is None or end > best[2] or (end == best[2] and i >= best[1]):
                best = (body, i, end)

    def walk_body(body: list[ast.stmt]) -> None:
        consider(body)
        for stmt in body:
            if isinstance(
                stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            for attr in ("body", "orelse", "finalbody"):
                child = getattr(stmt, attr, None)
                if isinstance(child, list) and child and isinstance(child[0], ast.stmt):
                    walk_body(child)
            if isinstance(stmt, ast.Try):
                for handler in stmt.handlers:
                    walk_body(handler.body)

    walk_body(construct.body)
    if best is None:
        return None
    return best[0], best[1]


def inject_early_exit(
    source: str, until_line: int, scene_name: str | None = None
) -> str:
    """Return source that raises ``EndSceneEarlyException`` after ``until_line``.

    The raise is **always** placed inside a ``construct()`` body so Manim can
    catch it while rendering. Module- / class-scope injection is never used.

    If ``until_line < 1``, or the cursor sits on class attributes / docstring
    above any ``construct`` statement, inserts the raise at the start of that
    scene's ``construct``.
    """
    tree = ast.parse(source)
    if not isinstance(tree, ast.Module):
        raise ValueError("expected a module")

    raise_stmt = ast.parse("raise EndSceneEarlyException()").body[0]
    ast.fix_missing_locations(raise_stmt)

    if until_line < 1:
        construct = None
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if _is_construct(item):
                    construct = item
                    break
            if construct is not None:
                break
        if construct is None:
            raise ValueError("no construct() found to inject early exit")
        construct.body.insert(0, raise_stmt)
    else:
        construct = _find_construct(tree, until_line, scene_name)
        if construct is None:
            raise ValueError(
                f"no construct() found for line {until_line}"
                + (f" / scene {scene_name}" if scene_name else "")
            )
        anchor = _find_anchor_in_construct(construct, until_line)
        if anchor is None:
            # Class attribute / docstring / above construct body → start of construct.
            construct.body.insert(0, raise_stmt)
        else:
            body, idx = anchor
            body.insert(idx + 1, raise_stmt)

    _ensure_early_exit_import(tree)
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def snapshot_at_line(
    file_path: str | Path,
    scene_name: str,
    active_until_line: int,
    *,
    source: str | None = None,
    quality: str = "l",
    timeout: int | None = DEFAULT_TIMEOUT,
    cache_dir: str | Path | None = None,
    manim_cmd: list[str] | None = None,
) -> SnapshotResult:
    path = Path(file_path).resolve()
    cwd = path.parent if path.is_file() else Path.cwd()

    if source is None:
        if not path.is_file():
            return SnapshotResult(
                ok=False,
                path=str(path),
                scene=scene_name,
                active_until_line=active_until_line,
                quality=quality,
                error=f"file not found: {path}",
            )
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            return SnapshotResult(
                ok=False,
                path=str(path),
                scene=scene_name,
                active_until_line=active_until_line,
                quality=quality,
                error=str(exc),
            )

    key = snapshot_cache_key(
        source, scene_name, active_until_line, quality=quality
    )
    cache_root = Path(cache_dir) if cache_dir else _default_cache_dir()
    cache_root.mkdir(parents=True, exist_ok=True)
    cached_png = cache_root / f"{key}.png"

    base = SnapshotResult(
        ok=False,
        path=str(path),
        scene=scene_name,
        active_until_line=active_until_line,
        quality=quality,
        cache_key=key,
    )

    if cached_png.is_file() and cached_png.stat().st_size > 0:
        w, h = _png_size(cached_png)
        base.ok = True
        base.cached = True
        base.png_path = str(cached_png.resolve())
        base.width = w
        base.height = h
        return base

    try:
        transformed = inject_early_exit(
            source, active_until_line, scene_name=scene_name
        )
    except (SyntaxError, ValueError) as exc:
        base.error = f"snapshot transform failed: {exc}"
        return base

    # Need a real path for Manim cwd/imports; write beside source file when possible.
    write_cwd = cwd if path.is_file() else Path.cwd()
    write_path = path if path.is_file() else write_cwd / f"{scene_name}.py"
    temp_path: Path | None = None
    try:
        temp_path = _write_temp_render_source(
            write_cwd, write_path, transformed, prefix_tag="snap"
        )
    except Exception as exc:  # noqa: BLE001
        base.error = f"failed to write temp snapshot file: {exc}"
        return base

    cmd = list(manim_cmd or resolve_manim_cmd())
    cmd.append(_quality_flag(quality))
    cmd.append("-s")  # save last frame (PNG); skips animation encoding
    cmd.extend([str(temp_path), scene_name])
    base.command = cmd

    effective_timeout = DEFAULT_TIMEOUT if timeout is None else timeout
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(write_cwd),
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            check=False,
        )
    except FileNotFoundError:
        base.error = "manim executable not found — install ManimCE or set PATH"
        return base
    except subprocess.TimeoutExpired:
        base.error = f"snapshot timed out after {effective_timeout}s"
        return base
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    log = "\n".join(
        part for part in (proc.stdout or "", proc.stderr or "") if part
    ).strip()
    base.log_tail = log[-4000:] if len(log) > 4000 else log
    base.returncode = proc.returncode

    output = _extract_png_path(log)
    if output is None:
        output = _find_newest_png(write_cwd / "media", scene_name)

    if proc.returncode != 0:
        base.error = f"manim exited with code {proc.returncode}"
        return base
    if not output:
        base.error = "snapshot finished but PNG was not found"
        return base

    src_png = Path(output)
    if not src_png.is_file():
        base.error = f"PNG missing: {output}"
        return base

    try:
        shutil.copy2(src_png, cached_png)
        png_path = cached_png
    except OSError:
        png_path = src_png

    w, h = _png_size(png_path)
    base.ok = True
    base.png_path = str(png_path.resolve())
    base.width = w
    base.height = h
    return base

"""ManimCE still capture for Stage at a source line (Phase 12).

Uses a temp sibling file + ``raise EndSceneEarlyException`` after the until-line
statement, then in-process last-frame render (preferred) or ``manim -ql -s``.
Does not rewrite the user's on-disk scene. Uninstall-safe — no plugin Scene base
class.

Cache keys use a **construct prefix digest** (plus local import fingerprint) so
edits after the cursor / in other scene classes do not invalidate earlier stills.

Intentionally does **not** import ``manim_dock.render`` (libcst): still capture
only needs stdlib + a Manim-capable interpreter.
"""

from __future__ import annotations

import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SNAPSHOT_VERSION = "v6-strip-elide"
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
    #: ``cache`` | ``inprocess`` | ``cli`` | ```` — how the PNG was produced.
    engine: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _stmt_contains(root: ast.AST, target: ast.AST) -> bool:
    for node in ast.walk(root):
        if node is target:
            return True
    return False


def _truncate_stmt_list(
    stmts: list[ast.stmt], anchor: ast.AST, past: list[bool]
) -> list[ast.stmt]:
    """Keep statements that run at or before ``anchor``; drop the rest."""
    if past[0]:
        return []
    out: list[ast.stmt] = []
    for stmt in stmts:
        if past[0]:
            break
        if stmt is anchor:
            out.append(stmt)
            past[0] = True
            break
        if _stmt_contains(stmt, anchor):
            out.append(_truncate_node(stmt, anchor, past))
            past[0] = True
            break
        out.append(stmt)
    return out


def _truncate_node(stmt: ast.stmt, anchor: ast.AST, past: list[bool]) -> ast.stmt:
    """Return a copy of ``stmt`` with bodies truncated at ``anchor``."""
    cloned = copy.copy(stmt)
    for field_name, value in ast.iter_fields(stmt):
        if (
            field_name in {"body", "orelse", "finalbody"}
            and isinstance(value, list)
            and value
            and isinstance(value[0], ast.stmt)
        ):
            setattr(
                cloned,
                field_name,
                _truncate_stmt_list(value, anchor, past),
            )
        elif field_name == "handlers" and isinstance(value, list):
            new_handlers: list[ast.AST] = []
            for handler in value:
                if past[0]:
                    break
                if handler is anchor or _stmt_contains(handler, anchor):
                    new_handlers.append(_truncate_node(handler, anchor, past))
                    past[0] = True
                    break
                new_handlers.append(handler)
            setattr(cloned, field_name, new_handlers)
    return cloned


def construct_prefix_canonical(
    source: str, scene_name: str, active_until_line: int
) -> str:
    """Canonical AST bytes for the scene construct prefix through the Stage anchor.

    Edits after the anchor, or in other scene classes in the same file, do not
    change this string. Whitespace-only / comment-only edits outside the kept
    AST also do not (``ast.dump`` without attributes).
    """
    from manim_dock.stage_transform import (
        construct_prefix_index,
        prefix_from_index,
    )

    indexed = construct_prefix_index(source, scene_name)
    if isinstance(indexed, str):
        return indexed
    header, stmts = indexed
    return prefix_from_index(header, stmts, active_until_line)


def local_import_fingerprint(file_path: str | Path | None, source: str) -> str:
    """Hash mtimes of same-directory modules imported by ``source``."""
    if file_path is None:
        return "nopath"
    path = Path(file_path)
    cwd = path.parent if path.suffix else path
    if not cwd.is_dir():
        return "nodir"
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "syntax"
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # relative — resolve first segment against cwd
                if node.module:
                    names.add(node.module.split(".")[0])
            elif node.module:
                names.add(node.module.split(".")[0])
    parts: list[str] = []
    for name in sorted(names):
        candidate = cwd / f"{name}.py"
        if candidate.is_file():
            try:
                st = candidate.stat()
                parts.append(f"{candidate.name}:{st.st_mtime_ns}:{st.st_size}")
            except OSError:
                continue
    return "|".join(parts) if parts else "nolocal"


def snapshot_cache_key(
    source: str,
    scene_name: str,
    active_until_line: int,
    *,
    quality: str = "l",
    file_path: str | Path | None = None,
    stage_elide_section: str | None = None,
    prefix: str | None = None,
    imports: str | None = None,
) -> str:
    """Content-addressed key for a Stage still (prefix digest, not whole file)."""
    prefix_val = (
        prefix
        if prefix is not None
        else construct_prefix_canonical(source, scene_name, active_until_line)
    )
    imports_val = (
        imports
        if imports is not None
        else local_import_fingerprint(file_path, source)
    )
    payload = "\0".join(
        [
            SNAPSHOT_VERSION,
            (quality or "l").strip().lower(),
            scene_name,
            str(active_until_line),
            prefix_val,
            imports_val,
            f"elide:{stage_elide_section}" if stage_elide_section else "elide:",
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
    """Statement to finish before the Stage still.

    Prefer the innermost executable statement that **contains** ``until_line``
    (so a multi-line ``self.play(...)`` / ``MathTex(...)`` runs to completion
    even when the cursor is on its first line). Otherwise fall back to the last
    statement with ``end_lineno <= until_line`` (blank line / between stmts).

    Never anchors on nested ``ClassDef`` / ``FunctionDef``.
    """
    # body, idx, start, end — containing cursor
    containing: tuple[list[ast.stmt], int, int, int] | None = None
    # body, idx, end — last finished at/before cursor
    finished: tuple[list[ast.stmt], int, int] | None = None

    def consider(body: list[ast.stmt]) -> None:
        nonlocal containing, finished
        for i, stmt in enumerate(body):
            if isinstance(
                stmt, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
            ):
                continue
            start = int(getattr(stmt, "lineno", 0) or 0)
            end = _stmt_end_line(stmt)
            if end <= 0:
                continue
            if start <= until_line <= end:
                span = end - start
                if containing is None:
                    containing = (body, i, start, end)
                else:
                    prev_span = containing[3] - containing[2]
                    # Innermost wins (tightest span); tie → later in same body.
                    if span < prev_span or (
                        span == prev_span and end >= containing[3] and i >= containing[1]
                    ):
                        containing = (body, i, start, end)
            if end <= until_line:
                if finished is None or end > finished[2] or (
                    end == finished[2] and i >= finished[1]
                ):
                    finished = (body, i, end)

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
    if containing is not None:
        return containing[0], containing[1]
    if finished is not None:
        return finished[0], finished[1]
    return None


def inject_early_exit(
    source: str, until_line: int, scene_name: str | None = None
) -> str:
    """Return source that raises ``EndSceneEarlyException`` after the cursor stmt.

    The raise is **always** placed inside a ``construct()`` body so Manim can
    catch it while rendering. Module- / class-scope injection is never used.

    When ``until_line`` falls inside a (possibly multi-line) statement, that
    whole statement runs first — Stage shows the still *after* the command.
    Blank lines fall back to the last finished statement.

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


def _quality_tempconfig(quality: str) -> str:
    q = (quality or "l").strip().lower()
    return {
        "l": "low_quality",
        "low": "low_quality",
        "ql": "low_quality",
        "m": "medium_quality",
        "medium": "medium_quality",
        "h": "high_quality",
        "high": "high_quality",
        "k": "fourk_quality",
        "4k": "fourk_quality",
    }.get(q, "low_quality")


def _finish_cached_png(
    base: SnapshotResult, src_png: Path, cached_png: Path, *, engine: str
) -> SnapshotResult:
    try:
        shutil.copy2(src_png, cached_png)
        png_path = cached_png
    except OSError:
        png_path = src_png
    w, h = _png_size(png_path)
    base.ok = True
    base.engine = engine
    base.png_path = str(png_path.resolve())
    base.width = w
    base.height = h
    return base


def _capture_inprocess(
    *,
    write_cwd: Path,
    write_path: Path,
    transformed: str,
    scene_name: str,
    quality: str,
    cached_png: Path,
    base: SnapshotResult,
) -> SnapshotResult | None:
    """Render last frame in-process. Returns None if Manim is unavailable."""
    try:
        from manim import tempconfig  # type: ignore[import-not-found]
        from manim.utils.exceptions import (  # type: ignore[import-not-found]
            EndSceneEarlyException,
        )
    except Exception:
        return None

    temp_path: Path | None = None
    media_root = cached_png.parent / f".inproc_{cached_png.stem[:16]}"
    try:
        temp_path = _write_temp_render_source(
            write_cwd, write_path, transformed, prefix_tag="snapip"
        )
        mod_name = f"manim_dock_snap_{cached_png.stem[:20]}"
        spec = importlib.util.spec_from_file_location(mod_name, temp_path)
        if spec is None or spec.loader is None:
            base.error = "failed to load temp snapshot module"
            return base
        module = importlib.util.module_from_spec(spec)
        # Ensure project cwd imports resolve during exec_module.
        sys_path_prefix = str(write_cwd)
        inserted = False
        if sys_path_prefix not in sys.path:
            sys.path.insert(0, sys_path_prefix)
            inserted = True
        prev_cwd = Path.cwd()
        try:
            os_chdir = __import__("os").chdir
            os_chdir(write_cwd)
            spec.loader.exec_module(module)
            scene_cls = getattr(module, scene_name, None)
            if scene_cls is None:
                base.error = f"scene class not found after load: {scene_name}"
                return base
            media_root.mkdir(parents=True, exist_ok=True)
            # PNG under Dock cache; reuse project Tex/texts (avoid cold LaTeX).
            project_media = write_cwd / "media"
            project_tex = project_media / "Tex"
            project_texts = project_media / "texts"
            project_tex.mkdir(parents=True, exist_ok=True)
            project_texts.mkdir(parents=True, exist_ok=True)
            cfg = {
                "quality": _quality_tempconfig(quality),
                "save_last_frame": True,
                "preview": False,
                "verbosity": "ERROR",
                "progress_bar": "none",
                "media_dir": str(media_root),
                "tex_dir": str(project_tex),
                "text_dir": str(project_texts),
                "disable_caching": True,
            }
            base.command = ["inprocess", scene_name, str(temp_path)]
            # Keep stdout clean for stdio RPC workers (Manim logs → buffer).
            from manim_dock.stage_transform import stage_fast_play_patches

            log_buf = io.StringIO()
            with (
                stage_fast_play_patches(),
                tempconfig(cfg),
                contextlib.redirect_stdout(log_buf),
            ):
                scene = scene_cls()
                try:
                    scene.render()
                except EndSceneEarlyException:
                    # Some Manim versions surface this; render usually catches it.
                    pass
            captured = log_buf.getvalue().strip()
            if captured:
                base.log_tail = captured[-4000:]
        finally:
            __import__("os").chdir(prev_cwd)
            if inserted:
                try:
                    sys.path.remove(sys_path_prefix)
                except ValueError:
                    pass
            sys.modules.pop(mod_name, None)

        png = _find_newest_png(media_root, scene_name)
        if not png:
            base.error = "in-process snapshot finished but PNG was not found"
            return base
        src = Path(png)
        if not src.is_file():
            base.error = f"PNG missing: {png}"
            return base
        return _finish_cached_png(base, src, cached_png, engine="inprocess")
    except Exception as exc:  # noqa: BLE001 — surface to Stage
        base.error = f"in-process snapshot failed: {exc}"
        return base
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        # Keep media_root for debugging hard failures; prune empty trees lightly.
        try:
            if media_root.is_dir() and not any(media_root.rglob("*.png")):
                shutil.rmtree(media_root, ignore_errors=True)
        except OSError:
            pass


def _capture_via_cli(
    *,
    write_cwd: Path,
    write_path: Path,
    transformed: str,
    scene_name: str,
    quality: str,
    timeout: int,
    manim_cmd: list[str] | None,
    cached_png: Path,
    base: SnapshotResult,
) -> SnapshotResult:
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
    cmd.append("-s")
    cmd.extend([str(temp_path), scene_name])
    base.command = cmd

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(write_cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        base.error = "manim executable not found — install ManimCE or set PATH"
        return base
    except subprocess.TimeoutExpired:
        base.error = f"snapshot timed out after {timeout}s"
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

    return _finish_cached_png(base, src_png, cached_png, engine="cli")


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
    prefer_inprocess: bool = True,
    skip_until_section: str | None = None,
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

    from manim_dock.stage_transform import (
        prepare_stage_source,
        resolve_stage_elide_section,
        strip_other_scene_classes,
    )

    elide_section = resolve_stage_elide_section(
        source,
        scene_name,
        active_until_line,
        section_hint=skip_until_section,
    )
    key = snapshot_cache_key(
        source,
        scene_name,
        active_until_line,
        quality=quality,
        file_path=path,
        stage_elide_section=elide_section,
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
        base.engine = "cache"
        base.png_path = str(cached_png.resolve())
        base.width = w
        base.height = h
        return base

    try:
        transformed = prepare_stage_source(
            source,
            scene_name,
            active_until_line,
            inject_early_exit=lambda src, line: inject_early_exit(
                src, line, scene_name=scene_name
            ),
            elide_section=elide_section,
        )
    except (SyntaxError, ValueError) as exc:
        base.error = f"snapshot transform failed: {exc}"
        return base

    write_cwd = cwd if path.is_file() else Path.cwd()
    write_path = path if path.is_file() else write_cwd / f"{scene_name}.py"
    effective_timeout = DEFAULT_TIMEOUT if timeout is None else timeout

    def _run_capture(code: str, png_path: Path) -> SnapshotResult:
        if prefer_inprocess:
            inproc = _capture_inprocess(
                write_cwd=write_cwd,
                write_path=write_path,
                transformed=code,
                scene_name=scene_name,
                quality=quality,
                cached_png=png_path,
                base=base,
            )
            if inproc is not None and inproc.ok:
                return inproc
            if (
                inproc is not None
                and inproc.error
                and "not found after load" in inproc.error
            ):
                return inproc
        return _capture_via_cli(
            write_cwd=write_cwd,
            write_path=write_path,
            transformed=code,
            scene_name=scene_name,
            quality=quality,
            timeout=effective_timeout,
            manim_cmd=manim_cmd,
            cached_png=png_path,
            base=base,
        )

    result = _run_capture(transformed, cached_png)
    if result.ok or not elide_section:
        return result

    # Elision can break sections that need prior locals — retry full prefix.
    try:
        fallback = inject_early_exit(
            source, active_until_line, scene_name=scene_name
        )
        fallback = strip_other_scene_classes(fallback, scene_name)
    except (SyntaxError, ValueError):
        return result
    fb_key = snapshot_cache_key(
        source,
        scene_name,
        active_until_line,
        quality=quality,
        file_path=path,
        stage_elide_section=None,
    )
    fb_png = cache_root / f"{fb_key}.png"
    base.cache_key = fb_key
    base.error = None
    base.ok = False
    base.engine = ""
    base.png_path = None
    if fb_png.is_file() and fb_png.stat().st_size > 0:
        return _finish_cached_png(base, fb_png, fb_png, engine="cache")
    return _run_capture(fallback, fb_png)

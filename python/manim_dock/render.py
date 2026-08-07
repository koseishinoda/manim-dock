"""Run ManimCE low-quality renders and locate the output media file."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import libcst as cst


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


def _is_self_next_section(call: cst.Call) -> bool:
    return (
        isinstance(call.func, cst.Attribute)
        and isinstance(call.func.value, cst.Name)
        and call.func.value.value == "self"
        and call.func.attr.value == "next_section"
    )


def _string_literal_value(node: cst.BaseExpression) -> str | None:
    if isinstance(node, cst.SimpleString):
        try:
            return node.evaluated_value
        except Exception:
            raw = node.value
            if len(raw) >= 2 and raw[0] in {"'", '"'} and raw[-1] == raw[0]:
                return raw[1:-1]
    return None


def _section_name_from_call(call: cst.Call) -> str | None:
    """Detect section name from ``self.next_section("Name")`` or ``name="Name"``."""
    for arg in call.args:
        if arg.keyword is None:
            return _string_literal_value(arg.value)
    for arg in call.args:
        if arg.keyword is not None and arg.keyword.value == "name":
            return _string_literal_value(arg.value)
    return None


def _ensure_skip_animations_true(call: cst.Call) -> cst.Call:
    """Set or add ``skip_animations=True`` on a ``next_section`` call."""
    new_args: list[cst.Arg] = []
    found = False
    for arg in call.args:
        if arg.keyword is not None and arg.keyword.value == "skip_animations":
            found = True
            new_args.append(arg.with_changes(value=cst.Name("True")))
        else:
            new_args.append(arg)
    if not found:
        if new_args:
            last = new_args[-1]
            if isinstance(last.comma, cst.Comma):
                after = last.comma.whitespace_after
                if isinstance(after, cst.SimpleWhitespace) and after.value == "":
                    new_args[-1] = last.with_changes(
                        comma=last.comma.with_changes(
                            whitespace_after=cst.SimpleWhitespace(" ")
                        )
                    )
            else:
                # None or MaybeSentinel — force an explicit comma before the new kwarg.
                new_args[-1] = last.with_changes(
                    comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
                )
        new_args.append(
            cst.Arg(
                value=cst.Name("True"),
                keyword=cst.Name("skip_animations"),
                equal=cst.AssignEqual(
                    whitespace_before=cst.SimpleWhitespace(""),
                    whitespace_after=cst.SimpleWhitespace(""),
                ),
            )
        )
    return call.with_changes(args=new_args)


def _strip_skip_animations(call: cst.Call) -> cst.Call:
    """Remove ``skip_animations=...`` so the section plays normally."""
    cleaned: list[cst.Arg] = []
    removed = False
    for arg in call.args:
        if arg.keyword is not None and arg.keyword.value == "skip_animations":
            removed = True
            continue
        cleaned.append(arg)
    if not removed:
        return call
    if cleaned and isinstance(cleaned[-1].comma, cst.Comma):
        cleaned[-1] = cleaned[-1].with_changes(comma=cst.MaybeSentinel.DEFAULT)
    return call.with_changes(args=cleaned)


class _SkipUntilSectionTransformer(cst.CSTTransformer):
    def __init__(self, section_name: str) -> None:
        self.section_name = section_name
        self.found_target = False

    def leave_Call(
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.Call:
        if not _is_self_next_section(original_node):
            return updated_node
        name = _section_name_from_call(original_node)
        if name is None:
            return updated_node
        if name == self.section_name:
            self.found_target = True
            # Target must not skip.
            return _strip_skip_animations(updated_node)
        if not self.found_target:
            return _ensure_skip_animations_true(updated_node)
        return updated_node


def _iter_section_names(module: cst.Module) -> list[str]:
    names: list[str] = []

    class _Collector(cst.CSTVisitor):
        def visit_Call(self, node: cst.Call) -> bool:
            if _is_self_next_section(node):
                name = _section_name_from_call(node)
                if name is not None:
                    names.append(name)
            return True

    module.visit(_Collector())
    return names


def _apply_skip_until_section(source: str, section_name: str) -> str:
    """Return source with ``skip_animations=True`` on sections before ``section_name``.

    Detects names from ``self.next_section("Name")`` or ``self.next_section(name="Name")``.
    The target section is left without skip. Later sections are unchanged.
    Raises ``ValueError`` if the target section name is not found.
    """
    if not section_name:
        raise ValueError("section_name must be non-empty")
    module = cst.parse_module(source)
    if section_name not in _iter_section_names(module):
        raise ValueError(f"section not found: {section_name!r}")
    transformer = _SkipUntilSectionTransformer(section_name)
    updated = module.visit(transformer)
    return updated.code


class _ConstructOnlyMethodTransformer(cst.CSTTransformer):
    """Rewrite ``Scene.construct`` body to ``self.<method>()``; keep other methods."""

    def __init__(self, scene_name: str, method_name: str) -> None:
        self.scene_name = scene_name
        self.method_name = method_name
        self.found_scene = False
        self.found_method = False
        self.rewrote_construct = False

    def leave_ClassDef(
        self, original_node: cst.ClassDef, updated_node: cst.ClassDef
    ) -> cst.ClassDef:
        if updated_node.name.value != self.scene_name:
            return updated_node
        self.found_scene = True
        body = updated_node.body
        if not isinstance(body, cst.IndentedBlock):
            return updated_node

        new_stmts: list[cst.BaseStatement] = []
        for stmt in body.body:
            if isinstance(stmt, cst.FunctionDef):
                if stmt.name.value == self.method_name:
                    self.found_method = True
                if stmt.name.value == "construct":
                    call = cst.parse_statement(f"self.{self.method_name}()\n")
                    stmt = stmt.with_changes(
                        body=cst.IndentedBlock(body=[call])
                    )
                    self.rewrote_construct = True
            new_stmts.append(stmt)

        return updated_node.with_changes(
            body=body.with_changes(body=new_stmts)
        )


def _construct_only_method(
    source: str, scene_name: str, method_name: str
) -> str:
    """Rewrite ``scene_name.construct`` to only call ``self.<method_name>()``.

    Other methods on the class are preserved. Raises ``ValueError`` if the
    scene, ``construct``, or target method is missing, or if ``method_name``
    is empty / ``construct``.
    """
    if not scene_name:
        raise ValueError("scene_name must be non-empty")
    if not method_name:
        raise ValueError("method_name must be non-empty")
    if method_name == "construct":
        raise ValueError("method_name cannot be 'construct'")

    module = cst.parse_module(source)
    transformer = _ConstructOnlyMethodTransformer(scene_name, method_name)
    updated = module.visit(transformer)
    if not transformer.found_scene:
        raise ValueError(f"scene not found: {scene_name!r}")
    if not transformer.found_method:
        raise ValueError(f"method not found: {method_name!r}")
    if not transformer.rewrote_construct:
        raise ValueError(f"construct not found on scene {scene_name!r}")
    return updated.code


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


def render_scene(
    file_path: str | Path,
    scene_name: str,
    *,
    quality: str = "l",
    manim_cmd: list[str] | None = None,
    preview: bool = False,
    timeout: int | None = 600,
    save_sections: bool = False,
    skip_until_section: str | None = None,
    method: str | None = None,
) -> RenderResult:
    path = Path(file_path).resolve()
    if not path.is_file():
        return RenderResult(ok=False, error=f"file not found: {path}")

    cwd = path.parent
    render_path = path
    temp_path: Path | None = None

    if method or skip_until_section:
        try:
            source = path.read_text(encoding="utf-8")
            transformed = source
            if method:
                transformed = _construct_only_method(
                    transformed, scene_name, method
                )
            if skip_until_section:
                transformed = _apply_skip_until_section(
                    transformed, skip_until_section
                )
        except ValueError as exc:
            return RenderResult(ok=False, error=str(exc), cwd=str(cwd))
        except Exception as exc:  # noqa: BLE001 — surface parse failures
            kind = "method" if method else "skip_until_section"
            return RenderResult(
                ok=False,
                error=f"{kind} transform failed: {exc}",
                cwd=str(cwd),
            )
        tag = "method" if method else "skip"
        try:
            temp_path = _write_temp_render_source(
                cwd, path, transformed, prefix_tag=tag
            )
        except Exception as exc:  # noqa: BLE001
            return RenderResult(
                ok=False,
                error=f"failed to write temp render file: {exc}",
                cwd=str(cwd),
            )
        render_path = temp_path

    cmd = list(manim_cmd or resolve_manim_cmd())
    # Classic ManimCE CLI form (widely compatible). No `-p`: Dock shows the video.
    cmd.append(_quality_flag(quality))
    if save_sections:
        cmd.append("--save_sections")
    cmd.extend(
        [
            str(render_path),
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
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

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

"""Surgical insert patches via libcst — propose only; host applies after confirm.

Insert ``self.wait(...)`` / ``self.play(...)`` after a statement in a function body
(typically after ``self.play`` / ``self.wait`` / ``self.next_section``).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

import libcst as cst

from manim_dock.patch_timing import (
    _fmt_num,
    _is_next_section_stmt,
    _is_play_or_wait_stmt,
)


@dataclass
class InsertPatchProposal:
    ok: bool
    path: str
    kind: str
    after_line: int
    original: str
    proposed: str
    diff: str
    error: str | None = None
    summary: str = ""
    duration: float | None = None
    anim_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "kind": self.kind,
            "after_line": self.after_line,
            "original": self.original,
            "proposed": self.proposed,
            "diff": self.diff,
            "error": self.error,
            "summary": self.summary,
            "duration": self.duration,
            "anim_code": self.anim_code,
        }


def _is_preferred_anchor(stmt: cst.CSTNode) -> bool:
    return _is_play_or_wait_stmt(stmt) or _is_next_section_stmt(stmt)


def _make_wait_stmt(duration: float) -> cst.SimpleStatementLine:
    expr = cst.parse_expression(f"self.wait({_fmt_num(duration)})")
    return cst.SimpleStatementLine(body=[cst.Expr(value=expr)])


def _make_play_stmt(anim_code: str) -> cst.SimpleStatementLine:
    # Validate inner expression first for clearer errors.
    cst.parse_expression(anim_code)
    expr = cst.parse_expression(f"self.play({anim_code})")
    return cst.SimpleStatementLine(body=[cst.Expr(value=expr)])


class _InsertPatcher(cst.CSTTransformer):
    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, after_line: int, new_stmt: cst.SimpleStatementLine) -> None:
        self.after_line = after_line
        self.new_stmt = new_stmt
        self.patched = False
        self.error: str | None = None
        self.preferred_anchor = False

    def _maybe_patch(
        self,
        original_node: cst.FunctionDef | cst.AsyncFunctionDef,
        updated_node: cst.FunctionDef | cst.AsyncFunctionDef,
    ) -> cst.FunctionDef | cst.AsyncFunctionDef:
        if self.patched or self.error is not None:
            return updated_node

        orig_block = original_node.body
        if not isinstance(orig_block, cst.IndentedBlock):
            return updated_node

        idx: int | None = None
        anchor_stmt: cst.CSTNode | None = None
        for i, stmt in enumerate(orig_block.body):
            try:
                pos = self.get_metadata(cst.metadata.PositionProvider, stmt)
            except Exception:
                continue
            if pos is None:
                continue
            if pos.start.line == self.after_line:
                idx = i
                anchor_stmt = stmt
                break

        if idx is None or anchor_stmt is None:
            return updated_node

        upd_block = updated_node.body
        if not isinstance(upd_block, cst.IndentedBlock):
            return updated_node

        self.preferred_anchor = _is_preferred_anchor(anchor_stmt)
        statements = list(upd_block.body)
        statements.insert(idx + 1, self.new_stmt)
        self.patched = True
        return updated_node.with_changes(
            body=upd_block.with_changes(body=statements)
        )

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]

    def leave_AsyncFunctionDef(
        self, original_node: cst.AsyncFunctionDef, updated_node: cst.AsyncFunctionDef
    ) -> cst.AsyncFunctionDef:
        return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]


def _propose_insert(
    source: str,
    *,
    path: str,
    kind: str,
    after_line: int,
    new_stmt: cst.SimpleStatementLine,
    summary: str,
    duration: float | None = None,
    anim_code: str | None = None,
) -> InsertPatchProposal:
    def _fail(error: str) -> InsertPatchProposal:
        return InsertPatchProposal(
            ok=False,
            path=path,
            kind=kind,
            after_line=after_line,
            original=source,
            proposed=source,
            diff="",
            error=error,
            duration=duration,
            anim_code=anim_code,
        )

    if after_line < 1:
        return _fail("after_line must be a positive 1-based line number")

    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"libcst parse failed: {exc}")

    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _InsertPatcher(after_line, new_stmt)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return _fail(f"patch failed: {exc}")

    if patcher.error is not None:
        return _fail(patcher.error)

    if not patcher.patched:
        return _fail(
            f"no statement starting on line {after_line} inside a function body"
        )

    proposed = new_module.code
    if proposed == source:
        return _fail("patch produced no textual change")

    diff = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=path,
            tofile=f"{path} (proposed)",
        )
    )
    note = summary
    if not patcher.preferred_anchor:
        note = f"{summary} (anchor is not play/wait/next_section)"
    return InsertPatchProposal(
        ok=True,
        path=path,
        kind=kind,
        after_line=after_line,
        original=source,
        proposed=proposed,
        diff=diff,
        summary=note,
        duration=duration,
        anim_code=anim_code,
    )


def propose_insert_wait(
    source: str,
    *,
    path: str,
    after_line: int,
    duration: float = 0.5,
) -> InsertPatchProposal:
    """Insert ``self.wait(duration)`` after the statement starting on ``after_line``."""
    if duration < 0:
        return InsertPatchProposal(
            ok=False,
            path=path,
            kind="insert_wait",
            after_line=after_line,
            original=source,
            proposed=source,
            diff="",
            error="duration must be non-negative",
            duration=duration,
        )
    try:
        new_stmt = _make_wait_stmt(duration)
    except Exception as exc:  # noqa: BLE001
        return InsertPatchProposal(
            ok=False,
            path=path,
            kind="insert_wait",
            after_line=after_line,
            original=source,
            proposed=source,
            diff="",
            error=f"could not build wait statement: {exc}",
            duration=duration,
        )
    return _propose_insert(
        source,
        path=path,
        kind="insert_wait",
        after_line=after_line,
        new_stmt=new_stmt,
        summary=f"insert self.wait({_fmt_num(duration)}) after L{after_line}",
        duration=duration,
    )


def propose_insert_play(
    source: str,
    *,
    path: str,
    after_line: int,
    anim_code: str = "FadeIn(Dot())",
) -> InsertPatchProposal:
    """Insert ``self.play(<anim_code>)`` after the statement starting on ``after_line``."""
    code = (anim_code or "").strip()
    if not code:
        return InsertPatchProposal(
            ok=False,
            path=path,
            kind="insert_play",
            after_line=after_line,
            original=source,
            proposed=source,
            diff="",
            error="anim_code must be a non-empty expression",
            anim_code=anim_code,
        )
    try:
        new_stmt = _make_play_stmt(code)
    except Exception as exc:  # noqa: BLE001
        return InsertPatchProposal(
            ok=False,
            path=path,
            kind="insert_play",
            after_line=after_line,
            original=source,
            proposed=source,
            diff="",
            error=f"invalid anim_code: {exc}",
            anim_code=anim_code,
        )
    return _propose_insert(
        source,
        path=path,
        kind="insert_play",
        after_line=after_line,
        new_stmt=new_stmt,
        summary=f"insert self.play({code}) after L{after_line}",
        anim_code=code,
    )


def propose_insert_wait_file(
    path: str, after_line: int, duration: float = 0.5
) -> InsertPatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_insert_wait(
        source, path=path, after_line=after_line, duration=duration
    )


def propose_insert_play_file(
    path: str, after_line: int, anim_code: str = "FadeIn(Dot())"
) -> InsertPatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_insert_play(
        source, path=path, after_line=after_line, anim_code=anim_code
    )


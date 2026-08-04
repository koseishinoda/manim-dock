"""Surgical layout patches via libcst — propose only; host applies after confirm."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any

import libcst as cst


def _fmt_num(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text not in {"", "-", "-0"} else "0"


def shift_expr_code(dx: float, dy: float) -> str:
    """Build a Manim vector expression preferring relative axes (G4)."""
    parts: list[str] = []
    if abs(dx) > 1e-9:
        if dx >= 0:
            parts.append(f"RIGHT * {_fmt_num(dx)}")
        else:
            parts.append(f"LEFT * {_fmt_num(-dx)}")
    if abs(dy) > 1e-9:
        if dy >= 0:
            parts.append(f"UP * {_fmt_num(dy)}")
        else:
            parts.append(f"DOWN * {_fmt_num(-dy)}")
    if not parts:
        return "ORIGIN"
    return " + ".join(parts)


@dataclass
class PatchProposal:
    ok: bool
    path: str
    name: str
    dx: float
    dy: float
    original: str
    proposed: str
    diff: str
    error: str | None = None
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "path": self.path,
            "name": self.name,
            "dx": self.dx,
            "dy": self.dy,
            "original": self.original,
            "proposed": self.proposed,
            "diff": self.diff,
            "error": self.error,
            "summary": self.summary,
        }


def _stmt_mentions_name_binding(stmt: cst.SimpleStatementLine, name: str) -> bool:
    if len(stmt.body) != 1:
        return False
    body = stmt.body[0]
    if isinstance(body, cst.Assign):
        for target in body.targets:
            if isinstance(target.target, cst.Name) and target.target.value == name:
                return True
    if isinstance(body, cst.AnnAssign) and isinstance(body.target, cst.Name):
        return body.target.value == name
    return False


def _stmt_is_name_attr_call(
    stmt: cst.SimpleStatementLine, name: str, attrs: frozenset[str] | None = None
) -> bool:
    if len(stmt.body) != 1 or not isinstance(stmt.body[0], cst.Expr):
        return False
    call = stmt.body[0].value
    if not isinstance(call, cst.Call) or not isinstance(call.func, cst.Attribute):
        return False
    if not isinstance(call.func.value, cst.Name) or call.func.value.value != name:
        return False
    if attrs is not None and call.func.attr.value not in attrs:
        return False
    return True


_LAYOUT_ATTRS = frozenset(
    {
        "to_edge",
        "to_corner",
        "move_to",
        "shift",
        "next_to",
        "arrange",
        "center",
        "align_to",
        "set_x",
        "set_y",
    }
)


def _patch_function_body(
    body: cst.BaseSuite, name: str, expr: str
) -> tuple[cst.BaseSuite, str | None]:
    """Insert ``name.shift(...)`` after the latest binding/layout call for ``name``.

    Always inserts (never replaces) so successive Stage drags accumulate correctly.
    """
    if not isinstance(body, cst.IndentedBlock):
        return body, None

    statements = list(body.body)
    last_anchor: int | None = None

    for i, stmt in enumerate(statements):
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        if _stmt_mentions_name_binding(stmt, name) or _stmt_is_name_attr_call(
            stmt, name, _LAYOUT_ATTRS
        ):
            last_anchor = i

    if last_anchor is None:
        return body, None

    shift_stmt = cst.parse_statement(f"{name}.shift({expr})\n")
    statements[last_anchor + 1 : last_anchor + 1] = [shift_stmt]
    return body.with_changes(body=statements), "insert"


class _ShiftPatcherWithLines(cst.CSTTransformer):
    """Patch the function whose body contains ``anchor_line`` (1-based)."""

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, name: str, dx: float, dy: float, anchor_line: int | None) -> None:
        self.name = name
        self.expr = shift_expr_code(dx, dy)
        self.anchor_line = anchor_line
        self.action: str | None = None
        self.saw_name = False

    def _maybe_patch(
        self,
        original_node: cst.FunctionDef | cst.AsyncFunctionDef,
        updated_node: cst.FunctionDef | cst.AsyncFunctionDef,
    ) -> cst.FunctionDef | cst.AsyncFunctionDef:
        if self.action is not None:
            return updated_node

        if self.anchor_line is not None:
            try:
                pos = self.get_metadata(cst.metadata.PositionProvider, original_node)
            except Exception:
                pos = None
            if pos is None:
                return updated_node
            if not (pos.start.line <= self.anchor_line <= pos.end.line):
                return updated_node
        else:
            mentions = False
            block = original_node.body
            stmts = block.body if isinstance(block, cst.IndentedBlock) else []
            for stmt in stmts:
                if isinstance(stmt, cst.SimpleStatementLine) and (
                    _stmt_mentions_name_binding(stmt, self.name)
                    or _stmt_is_name_attr_call(stmt, self.name, _LAYOUT_ATTRS)
                ):
                    mentions = True
                    break
            if not mentions:
                return updated_node

        new_body, action = _patch_function_body(updated_node.body, self.name, self.expr)
        if action is None:
            return updated_node
        self.saw_name = True
        self.action = action
        return updated_node.with_changes(body=new_body)

    def leave_FunctionDef(
        self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
    ) -> cst.FunctionDef:
        return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]

    def leave_AsyncFunctionDef(
        self, original_node: cst.AsyncFunctionDef, updated_node: cst.AsyncFunctionDef
    ) -> cst.AsyncFunctionDef:
        return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]


def propose_shift(
    source: str,
    *,
    path: str,
    name: str,
    dx: float,
    dy: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    if abs(dx) < 1e-9 and abs(dy) < 1e-9:
        return PatchProposal(
            ok=False,
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            original=source,
            proposed=source,
            diff="",
            error="delta is zero — nothing to patch",
        )

    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return PatchProposal(
            ok=False,
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            original=source,
            proposed=source,
            diff="",
            error=f"libcst parse failed: {exc}",
        )

    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _ShiftPatcherWithLines(name, dx, dy, anchor_line)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return PatchProposal(
            ok=False,
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            original=source,
            proposed=source,
            diff="",
            error=f"patch failed: {exc}",
        )

    if not patcher.saw_name or patcher.action is None:
        return PatchProposal(
            ok=False,
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            original=source,
            proposed=source,
            diff="",
            error=f"no binding or layout call found for {name!r}",
        )

    proposed = new_module.code
    if proposed == source:
        return PatchProposal(
            ok=False,
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            original=source,
            proposed=source,
            diff="",
            error="patch produced no textual change",
        )

    diff = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=path,
            tofile=f"{path} (proposed)",
        )
    )
    summary = f"{patcher.action} {name}.shift({shift_expr_code(dx, dy)})"
    return PatchProposal(
        ok=True,
        path=path,
        name=name,
        dx=dx,
        dy=dy,
        original=source,
        proposed=proposed,
        diff=diff,
        summary=summary,
    )


def propose_shift_file(
    path: str,
    name: str,
    dx: float,
    dy: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_shift(
        source, path=path, name=name, dx=dx, dy=dy, anchor_line=anchor_line
    )

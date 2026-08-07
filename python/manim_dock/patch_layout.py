"""Surgical layout patches via libcst — propose only; host applies after confirm."""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any, Sequence

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
        "scale",
    }
)

_BUFF_ATTRS = frozenset({"arrange", "next_to"})


def _is_numeric_literal(node: cst.BaseExpression) -> bool:
    if isinstance(node, (cst.Integer, cst.Float)):
        return True
    if isinstance(node, cst.UnaryOperation) and isinstance(node.operator, cst.Minus):
        return _is_numeric_literal(node.expression)
    return False


def _call_attr_name(call: cst.Call) -> str | None:
    if isinstance(call.func, cst.Attribute):
        return call.func.attr.value
    if isinstance(call.func, cst.Name):
        return call.func.value
    return None


def _is_surrounding_rectangle(call: cst.Call) -> bool:
    return isinstance(call.func, cst.Name) and call.func.value == "SurroundingRectangle"


def _args_mention_name(args: Sequence[cst.Arg], name: str) -> bool:
    for arg in args:
        if isinstance(arg.value, cst.Name) and arg.value.value == name:
            return True
    return False


def _chain_ends_with_attr(
    expr: cst.BaseExpression, attrs: frozenset[str]
) -> cst.Call | None:
    """Return Call if ``expr`` is ``(...).attr(...)`` with attr in ``attrs``."""
    if isinstance(expr, cst.Call) and isinstance(expr.func, cst.Attribute):
        if expr.func.attr.value in attrs:
            return expr
    return None


def _find_buff_call_in_stmt(stmt: cst.SimpleStatementLine, name: str) -> cst.Call | None:
    """Locate an editable arrange/next_to/SurroundingRectangle call for ``name``."""
    if len(stmt.body) != 1:
        return None
    body = stmt.body[0]

    if isinstance(body, cst.Expr) and isinstance(body.value, cst.Call):
        call = body.value
        if _stmt_is_name_attr_call(stmt, name, _BUFF_ATTRS):
            return call
        if _is_surrounding_rectangle(call) and _args_mention_name(call.args, name):
            return call
        return None

    if isinstance(body, cst.Assign):
        targets_name = any(
            isinstance(t.target, cst.Name) and t.target.value == name
            for t in body.targets
        )
        if targets_name:
            chained = _chain_ends_with_attr(body.value, _BUFF_ATTRS)
            if chained is not None:
                return chained
        if isinstance(body.value, cst.Call) and _is_surrounding_rectangle(body.value):
            if _args_mention_name(body.value.args, name):
                return body.value
        return None

    if isinstance(body, cst.AnnAssign) and isinstance(body.target, cst.Name):
        if body.target.value == name and body.value is not None:
            chained = _chain_ends_with_attr(body.value, _BUFF_ATTRS)
            if chained is not None:
                return chained
        if (
            isinstance(body.value, cst.Call)
            and _is_surrounding_rectangle(body.value)
            and _args_mention_name(body.value.args, name)
        ):
            return body.value

    return None


def _make_kw_arg(keyword: str, value: cst.BaseExpression) -> cst.Arg:
    return cst.Arg(
        keyword=cst.Name(keyword),
        equal=cst.AssignEqual(
            whitespace_before=cst.SimpleWhitespace(""),
            whitespace_after=cst.SimpleWhitespace(""),
        ),
        value=value,
    )


def _ensure_trailing_comma(args: list[cst.Arg]) -> None:
    if not args:
        return
    last = args[-1]
    if isinstance(last, cst.Arg) and last.comma is None:
        args[-1] = last.with_changes(
            comma=cst.Comma(whitespace_after=cst.SimpleWhitespace(" "))
        )


def _set_numeric_kw_or_positional(
    call: cst.Call,
    *,
    keyword: str,
    value: float,
    positional_index: int | None,
) -> cst.Call | None:
    """Update ``keyword=`` literal, else positional numeric slot, else insert kw."""
    new_val = cst.parse_expression(_fmt_num(value))
    args = list(call.args)

    for i, arg in enumerate(args):
        if (
            isinstance(arg, cst.Arg)
            and arg.keyword is not None
            and arg.keyword.value == keyword
        ):
            if not _is_numeric_literal(arg.value):
                return None
            args[i] = arg.with_changes(value=new_val)
            return call.with_changes(args=args)

    if positional_index is not None:
        positionals = [
            (i, a)
            for i, a in enumerate(args)
            if isinstance(a, cst.Arg) and a.keyword is None
        ]
        if len(positionals) > positional_index:
            i, arg = positionals[positional_index]
            if _is_numeric_literal(arg.value):
                args[i] = arg.with_changes(value=new_val)
                return call.with_changes(args=args)

    _ensure_trailing_comma(args)
    args.append(_make_kw_arg(keyword, new_val))
    return call.with_changes(args=args)


def _patch_buff_on_call(call: cst.Call, buff: float) -> cst.Call | None:
    attr = _call_attr_name(call)
    positional_index: int | None = None
    if attr == "arrange":
        positional_index = 1  # arrange(direction, buff, ...)
    elif attr == "next_to":
        positional_index = 2  # next_to(mobject, direction, buff, ...)
    return _set_numeric_kw_or_positional(
        call, keyword="buff", value=buff, positional_index=positional_index
    )


def _stmt_with_replaced_call(
    stmt: cst.SimpleStatementLine, old: cst.Call, new: cst.Call
) -> cst.SimpleStatementLine:
    """Replace ``old`` call inside a simple statement via object identity."""

    class _Replacer(cst.CSTTransformer):
        def leave_Call(
            self, original_node: cst.Call, updated_node: cst.Call
        ) -> cst.Call:
            if original_node is old:
                return new
            return updated_node

    result = stmt.visit(_Replacer())
    assert isinstance(result, cst.SimpleStatementLine)
    return result


def _patch_function_body_buff(
    body: cst.BaseSuite, name: str, buff: float
) -> tuple[cst.BaseSuite, str | None]:
    if not isinstance(body, cst.IndentedBlock):
        return body, None

    statements = list(body.body)
    last_idx: int | None = None
    last_call: cst.Call | None = None

    for i, stmt in enumerate(statements):
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        call = _find_buff_call_in_stmt(stmt, name)
        if call is not None:
            last_idx = i
            last_call = call

    if last_idx is None or last_call is None:
        return body, None

    patched_call = _patch_buff_on_call(last_call, buff)
    if patched_call is None:
        return body, "non_literal"

    old_stmt = statements[last_idx]
    assert isinstance(old_stmt, cst.SimpleStatementLine)
    statements[last_idx] = _stmt_with_replaced_call(old_stmt, last_call, patched_call)
    return body.with_changes(body=statements), "set"


def _literal_number(node: cst.BaseExpression) -> float | None:
    if isinstance(node, cst.Integer):
        try:
            return float(node.value)
        except ValueError:
            return None
    if isinstance(node, cst.Float):
        try:
            return float(node.value)
        except ValueError:
            return None
    if isinstance(node, cst.UnaryOperation) and isinstance(node.operator, cst.Minus):
        inner = _literal_number(node.expression)
        return None if inner is None else -inner
    return None


def _parse_shift_axis_term(node: cst.BaseExpression) -> tuple[float, float] | None:
    """Parse ``RIGHT``, ``LEFT * 0.5``, ``UP * n``, ``DOWN * n`` → (dx, dy)."""
    axis_map = {
        "RIGHT": (1.0, 0.0),
        "LEFT": (-1.0, 0.0),
        "UP": (0.0, 1.0),
        "DOWN": (0.0, -1.0),
    }
    if isinstance(node, cst.Name) and node.value in axis_map:
        return axis_map[node.value]
    if isinstance(node, cst.BinaryOperation) and isinstance(node.operator, cst.Multiply):
        left, right = node.left, node.right
        if isinstance(left, cst.Name) and left.value in axis_map:
            scale = _literal_number(right)
            if scale is None:
                return None
            ux, uy = axis_map[left.value]
            return ux * scale, uy * scale
        if isinstance(right, cst.Name) and right.value in axis_map:
            scale = _literal_number(left)
            if scale is None:
                return None
            ux, uy = axis_map[right.value]
            return ux * scale, uy * scale
    return None


def _parse_shift_vector(expr: cst.BaseExpression) -> tuple[float, float] | None:
    """Parse Dock-style ``shift(...)`` args into Manim (dx, dy)."""
    if isinstance(expr, cst.Name) and expr.value == "ORIGIN":
        return 0.0, 0.0
    term = _parse_shift_axis_term(expr)
    if term is not None:
        return term
    if isinstance(expr, cst.BinaryOperation) and isinstance(expr.operator, cst.Add):
        left = _parse_shift_vector(expr.left)
        right = _parse_shift_vector(expr.right)
        if left is None or right is None:
            return None
        return left[0] + right[0], left[1] + right[1]
    return None


def _shift_call_arg(
    stmt: cst.SimpleStatementLine, name: str
) -> cst.BaseExpression | None:
    if not _stmt_is_name_attr_call(stmt, name, frozenset({"shift"})):
        return None
    call = stmt.body[0].value
    assert isinstance(call, cst.Call)
    if len(call.args) != 1 or call.args[0].keyword is not None:
        return None
    return call.args[0].value


def _patch_function_body(
    body: cst.BaseSuite, name: str, stmt_code: str
) -> tuple[cst.BaseSuite, str | None]:
    """Insert ``stmt_code`` after the latest binding/layout call for ``name``."""
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

    insert_stmt = cst.parse_statement(f"{stmt_code}\n")
    statements[last_anchor + 1 : last_anchor + 1] = [insert_stmt]
    return body.with_changes(body=statements), "insert"


def _patch_function_body_shift(
    body: cst.BaseSuite, name: str, dx: float, dy: float
) -> tuple[cst.BaseSuite, str | None]:
    """Coalesce trailing ``name.shift(...)`` or insert a new one after the layout anchor.

    Successive Stage drags should rewrite one shift statement, not stack lines.
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

    # Trailing run of parseable ``name.shift(...)`` ending at last_anchor.
    run_start = last_anchor
    total_dx = 0.0
    total_dy = 0.0
    coalesce = False
    if isinstance(statements[last_anchor], cst.SimpleStatementLine):
        arg = _shift_call_arg(statements[last_anchor], name)  # type: ignore[arg-type]
        if arg is not None:
            parsed_run: list[tuple[int, float, float]] = []
            i = last_anchor
            while i >= 0 and isinstance(statements[i], cst.SimpleStatementLine):
                shift_arg = _shift_call_arg(statements[i], name)  # type: ignore[arg-type]
                if shift_arg is None:
                    break
                vec = _parse_shift_vector(shift_arg)
                if vec is None:
                    parsed_run = []
                    break
                parsed_run.append((i, vec[0], vec[1]))
                i -= 1
            if parsed_run:
                coalesce = True
                run_start = parsed_run[-1][0]
                for _, px, py in parsed_run:
                    total_dx += px
                    total_dy += py

    total_dx += dx
    total_dy += dy
    stmt_code = f"{name}.shift({shift_expr_code(total_dx, total_dy)})"
    new_stmt = cst.parse_statement(f"{stmt_code}\n")

    if coalesce:
        # Replace the whole trailing shift run with one statement.
        del statements[run_start : last_anchor + 1]
        statements[run_start:run_start] = [new_stmt]
        return body.with_changes(body=statements), "coalesce"

    statements[last_anchor + 1 : last_anchor + 1] = [new_stmt]
    return body.with_changes(body=statements), "insert"


def _function_mentions_name(
    node: cst.FunctionDef | cst.AsyncFunctionDef, name: str
) -> bool:
    block = node.body
    stmts = block.body if isinstance(block, cst.IndentedBlock) else []
    for stmt in stmts:
        if isinstance(stmt, cst.SimpleStatementLine) and (
            _stmt_mentions_name_binding(stmt, name)
            or _stmt_is_name_attr_call(stmt, name, _LAYOUT_ATTRS)
        ):
            return True
    return False


def _function_has_buff_site(
    node: cst.FunctionDef | cst.AsyncFunctionDef, name: str
) -> bool:
    block = node.body
    stmts = block.body if isinstance(block, cst.IndentedBlock) else []
    for stmt in stmts:
        if isinstance(stmt, cst.SimpleStatementLine) and _find_buff_call_in_stmt(
            stmt, name
        ):
            return True
    return False


class _InsertStmtPatcher(cst.CSTTransformer):
    """Insert a statement after the latest binding/layout anchor for ``name``."""

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(
        self, name: str, stmt_code: str, anchor_line: int | None
    ) -> None:
        self.name = name
        self.stmt_code = stmt_code
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
            if not _function_mentions_name(original_node, self.name):
                return updated_node

        new_body, action = _patch_function_body(
            updated_node.body, self.name, self.stmt_code
        )
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


class _ShiftPatcher(cst.CSTTransformer):
    """Insert or coalesce ``name.shift(...)`` after the layout anchor."""

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(
        self, name: str, dx: float, dy: float, anchor_line: int | None
    ) -> None:
        self.name = name
        self.dx = dx
        self.dy = dy
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
            if not _function_mentions_name(original_node, self.name):
                return updated_node

        new_body, action = _patch_function_body_shift(
            updated_node.body, self.name, self.dx, self.dy
        )
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


class _BuffPatcher(cst.CSTTransformer):
    """Patch buff= on the latest arrange/next_to/SurroundingRectangle for ``name``."""

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(self, name: str, buff: float, anchor_line: int | None) -> None:
        self.name = name
        self.buff = buff
        self.anchor_line = anchor_line
        self.action: str | None = None
        self.saw_name = False
        self.non_literal = False

    def _maybe_patch(
        self,
        original_node: cst.FunctionDef | cst.AsyncFunctionDef,
        updated_node: cst.FunctionDef | cst.AsyncFunctionDef,
    ) -> cst.FunctionDef | cst.AsyncFunctionDef:
        if self.action is not None or self.non_literal:
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
            if not _function_has_buff_site(original_node, self.name):
                return updated_node

        new_body, action = _patch_function_body_buff(
            updated_node.body, self.name, self.buff
        )
        if action == "non_literal":
            self.non_literal = True
            return updated_node
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


def _fail_proposal(
    *,
    path: str,
    name: str,
    dx: float,
    dy: float,
    source: str,
    error: str,
) -> PatchProposal:
    return PatchProposal(
        ok=False,
        path=path,
        name=name,
        dx=dx,
        dy=dy,
        original=source,
        proposed=source,
        diff="",
        error=error,
    )


def _success_proposal(
    *,
    path: str,
    name: str,
    dx: float,
    dy: float,
    source: str,
    proposed: str,
    summary: str,
) -> PatchProposal:
    diff = "".join(
        difflib.unified_diff(
            source.splitlines(keepends=True),
            proposed.splitlines(keepends=True),
            fromfile=path,
            tofile=f"{path} (proposed)",
        )
    )
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
        return _fail_proposal(
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            source=source,
            error="delta is zero — nothing to patch",
        )

    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            source=source,
            error=f"libcst parse failed: {exc}",
        )

    stmt_code = f"{name}.shift({shift_expr_code(dx, dy)})"
    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _ShiftPatcher(name, dx, dy, anchor_line)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            source=source,
            error=f"patch failed: {exc}",
        )

    if not patcher.saw_name or patcher.action is None:
        return _fail_proposal(
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            source=source,
            error=f"no binding or layout call found for {name!r}",
        )

    proposed = new_module.code
    if proposed == source:
        return _fail_proposal(
            path=path,
            name=name,
            dx=dx,
            dy=dy,
            source=source,
            error="patch produced no textual change",
        )

    # Summary reflects final coalesced expression when applicable.
    final_expr = shift_expr_code(dx, dy)
    if patcher.action == "coalesce":
        # Best-effort: show the written statement from the patched source.
        marker = f"{name}.shift("
        for line in proposed.splitlines():
            stripped = line.strip()
            if stripped.startswith(marker):
                final_expr = stripped[len(name) + 1 :]  # "shift(...)"
                break
        summary = f"coalesce {name}.{final_expr}"
    else:
        summary = f"{patcher.action} {stmt_code}"

    return _success_proposal(
        path=path,
        name=name,
        dx=dx,
        dy=dy,
        source=source,
        proposed=proposed,
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


def propose_buff(
    source: str,
    *,
    path: str,
    name: str,
    buff: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    """Propose editing ``buff`` on the latest arrange/next_to/SurroundingRectangle."""
    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=buff,
            dy=0.0,
            source=source,
            error=f"libcst parse failed: {exc}",
        )

    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _BuffPatcher(name, buff, anchor_line)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=buff,
            dy=0.0,
            source=source,
            error=f"patch failed: {exc}",
        )

    if patcher.non_literal:
        return _fail_proposal(
            path=path,
            name=name,
            dx=buff,
            dy=0.0,
            source=source,
            error=f"buff for {name!r} is not a numeric literal — refusing edit",
        )

    if not patcher.saw_name or patcher.action is None:
        return _fail_proposal(
            path=path,
            name=name,
            dx=buff,
            dy=0.0,
            source=source,
            error=f"no editable buff site found for {name!r}",
        )

    proposed = new_module.code
    if proposed == source:
        return _fail_proposal(
            path=path,
            name=name,
            dx=buff,
            dy=0.0,
            source=source,
            error="patch produced no textual change",
        )

    return _success_proposal(
        path=path,
        name=name,
        dx=buff,
        dy=0.0,
        source=source,
        proposed=proposed,
        summary=f"set {name} buff → {_fmt_num(buff)}",
    )


def propose_buff_file(
    path: str,
    name: str,
    buff: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_buff(
        source, path=path, name=name, buff=buff, anchor_line=anchor_line
    )


def propose_scale(
    source: str,
    *,
    path: str,
    name: str,
    factor: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    """Propose inserting ``name.scale(factor)`` after the latest binding/layout anchor."""
    if factor <= 0:
        return _fail_proposal(
            path=path,
            name=name,
            dx=factor,
            dy=0.0,
            source=source,
            error="scale factor must be > 0",
        )
    if abs(factor - 1.0) < 1e-9:
        return _fail_proposal(
            path=path,
            name=name,
            dx=factor,
            dy=0.0,
            source=source,
            error="scale factor is 1 — nothing to patch",
        )

    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=factor,
            dy=0.0,
            source=source,
            error=f"libcst parse failed: {exc}",
        )

    stmt_code = f"{name}.scale({_fmt_num(factor)})"
    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _InsertStmtPatcher(name, stmt_code, anchor_line)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=factor,
            dy=0.0,
            source=source,
            error=f"patch failed: {exc}",
        )

    if not patcher.saw_name or patcher.action is None:
        return _fail_proposal(
            path=path,
            name=name,
            dx=factor,
            dy=0.0,
            source=source,
            error=f"no binding or layout call found for {name!r}",
        )

    proposed = new_module.code
    if proposed == source:
        return _fail_proposal(
            path=path,
            name=name,
            dx=factor,
            dy=0.0,
            source=source,
            error="patch produced no textual change",
        )

    return _success_proposal(
        path=path,
        name=name,
        dx=factor,
        dy=0.0,
        source=source,
        proposed=proposed,
        summary=f"{patcher.action} {stmt_code}",
    )


def propose_scale_file(
    path: str,
    name: str,
    factor: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_scale(
        source, path=path, name=name, factor=factor, anchor_line=anchor_line
    )


_TEXT_CTORS = frozenset({"Text", "MarkupText", "MathTex", "Tex"})
_LAG_CTORS = frozenset({"LaggedStart", "AnimationGroup"})


def _find_text_ctor_call(expr: cst.BaseExpression) -> cst.Call | None:
    """Walk attribute chains to find Text/MarkupText/MathTex/Tex(...)."""
    current: cst.BaseExpression = expr
    while isinstance(current, cst.Call):
        if isinstance(current.func, cst.Name) and current.func.value in _TEXT_CTORS:
            return current
        if isinstance(current.func, cst.Attribute):
            current = current.func.value
            continue
        break
    return None


def _find_text_ctor_in_stmt(stmt: cst.SimpleStatementLine, name: str) -> cst.Call | None:
    if len(stmt.body) != 1:
        return None
    body = stmt.body[0]
    if isinstance(body, cst.Assign):
        targets_name = any(
            isinstance(t.target, cst.Name) and t.target.value == name
            for t in body.targets
        )
        if targets_name:
            return _find_text_ctor_call(body.value)
    if isinstance(body, cst.AnnAssign) and isinstance(body.target, cst.Name):
        if body.target.value == name and body.value is not None:
            return _find_text_ctor_call(body.value)
    return None


def _function_has_font_size_site(
    node: cst.FunctionDef | cst.AsyncFunctionDef, name: str
) -> bool:
    block = node.body
    stmts = block.body if isinstance(block, cst.IndentedBlock) else []
    for stmt in stmts:
        if isinstance(stmt, cst.SimpleStatementLine) and _find_text_ctor_in_stmt(
            stmt, name
        ):
            return True
    return False


def _patch_function_body_font_size(
    body: cst.BaseSuite, name: str, font_size: float
) -> tuple[cst.BaseSuite, str | None]:
    if not isinstance(body, cst.IndentedBlock):
        return body, None

    statements = list(body.body)
    last_idx: int | None = None
    last_call: cst.Call | None = None

    for i, stmt in enumerate(statements):
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        call = _find_text_ctor_in_stmt(stmt, name)
        if call is not None:
            last_idx = i
            last_call = call

    if last_idx is None or last_call is None:
        return body, None

    patched_call = _set_numeric_kw_or_positional(
        last_call, keyword="font_size", value=font_size, positional_index=None
    )
    if patched_call is None:
        return body, "non_literal"

    old_stmt = statements[last_idx]
    assert isinstance(old_stmt, cst.SimpleStatementLine)
    statements[last_idx] = _stmt_with_replaced_call(old_stmt, last_call, patched_call)
    return body.with_changes(body=statements), "set"


class _FontSizePatcher(cst.CSTTransformer):
    """Patch font_size= on the latest Text/MarkupText/MathTex/Tex binding for ``name``."""

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(
        self, name: str, font_size: float, anchor_line: int | None
    ) -> None:
        self.name = name
        self.font_size = font_size
        self.anchor_line = anchor_line
        self.action: str | None = None
        self.saw_name = False
        self.non_literal = False

    def _maybe_patch(
        self,
        original_node: cst.FunctionDef | cst.AsyncFunctionDef,
        updated_node: cst.FunctionDef | cst.AsyncFunctionDef,
    ) -> cst.FunctionDef | cst.AsyncFunctionDef:
        if self.action is not None or self.non_literal:
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
            if not _function_has_font_size_site(original_node, self.name):
                return updated_node

        new_body, action = _patch_function_body_font_size(
            updated_node.body, self.name, self.font_size
        )
        if action == "non_literal":
            self.non_literal = True
            return updated_node
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


def propose_font_size(
    source: str,
    *,
    path: str,
    name: str,
    font_size: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    """Propose setting ``font_size=`` on ``name = Text(...)/MathTex(...)/...``."""
    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=font_size,
            dy=0.0,
            source=source,
            error=f"libcst parse failed: {exc}",
        )

    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _FontSizePatcher(name, font_size, anchor_line)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=font_size,
            dy=0.0,
            source=source,
            error=f"patch failed: {exc}",
        )

    if patcher.non_literal:
        return _fail_proposal(
            path=path,
            name=name,
            dx=font_size,
            dy=0.0,
            source=source,
            error=f"font_size for {name!r} is not a numeric literal — refusing edit",
        )

    if not patcher.saw_name or patcher.action is None:
        return _fail_proposal(
            path=path,
            name=name,
            dx=font_size,
            dy=0.0,
            source=source,
            error=f"no Text/MarkupText/MathTex/Tex binding found for {name!r}",
        )

    proposed = new_module.code
    if proposed == source:
        return _fail_proposal(
            path=path,
            name=name,
            dx=font_size,
            dy=0.0,
            source=source,
            error="patch produced no textual change",
        )

    return _success_proposal(
        path=path,
        name=name,
        dx=font_size,
        dy=0.0,
        source=source,
        proposed=proposed,
        summary=f"set {name} font_size → {_fmt_num(font_size)}",
    )


def propose_font_size_file(
    path: str,
    name: str,
    font_size: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_font_size(
        source, path=path, name=name, font_size=font_size, anchor_line=anchor_line
    )


def _expr_mentions_name(expr: cst.CSTNode, name: str) -> bool:
    class _Finder(cst.CSTVisitor):
        def __init__(self) -> None:
            self.found = False

        def visit_Name(self, node: cst.Name) -> bool | None:
            if node.value == name:
                self.found = True
                return False
            return True

    finder = _Finder()
    expr.visit(finder)
    return finder.found


def _collect_lag_calls(stmt: cst.SimpleStatementLine) -> list[cst.Call]:
    found: list[cst.Call] = []

    class _Collector(cst.CSTVisitor):
        def visit_Call(self, node: cst.Call) -> bool | None:
            if isinstance(node.func, cst.Name) and node.func.value in _LAG_CTORS:
                found.append(node)
            return True

    stmt.visit(_Collector())
    return found


def _patch_function_body_lag_ratio(
    body: cst.BaseSuite, name: str, lag_ratio: float
) -> tuple[cst.BaseSuite, str | None]:
    if not isinstance(body, cst.IndentedBlock):
        return body, None

    statements = list(body.body)
    seen_binding = False
    # Prefer last call that mentions name; else last lag call after binding.
    best_mention: tuple[int, cst.Call] | None = None
    best_after: tuple[int, cst.Call] | None = None

    for i, stmt in enumerate(statements):
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        if _stmt_mentions_name_binding(stmt, name):
            seen_binding = True
        for call in _collect_lag_calls(stmt):
            if _expr_mentions_name(call, name):
                best_mention = (i, call)
            elif seen_binding:
                best_after = (i, call)

    chosen = best_mention or best_after
    if chosen is None:
        return body, None

    last_idx, last_call = chosen
    patched_call = _set_numeric_kw_or_positional(
        last_call, keyword="lag_ratio", value=lag_ratio, positional_index=None
    )
    if patched_call is None:
        return body, "non_literal"

    old_stmt = statements[last_idx]
    assert isinstance(old_stmt, cst.SimpleStatementLine)
    statements[last_idx] = _stmt_with_replaced_call(old_stmt, last_call, patched_call)
    return body.with_changes(body=statements), "set"


def _function_has_lag_site(
    node: cst.FunctionDef | cst.AsyncFunctionDef, name: str
) -> bool:
    block = node.body
    stmts = block.body if isinstance(block, cst.IndentedBlock) else []
    seen_binding = False
    for stmt in stmts:
        if not isinstance(stmt, cst.SimpleStatementLine):
            continue
        if _stmt_mentions_name_binding(stmt, name):
            seen_binding = True
        for call in _collect_lag_calls(stmt):
            if _expr_mentions_name(call, name) or seen_binding:
                return True
    return False


class _LagRatioPatcher(cst.CSTTransformer):
    """Patch lag_ratio= on LaggedStart/AnimationGroup related to ``name``."""

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    def __init__(
        self, name: str, lag_ratio: float, anchor_line: int | None
    ) -> None:
        self.name = name
        self.lag_ratio = lag_ratio
        self.anchor_line = anchor_line
        self.action: str | None = None
        self.saw_name = False
        self.non_literal = False

    def _maybe_patch(
        self,
        original_node: cst.FunctionDef | cst.AsyncFunctionDef,
        updated_node: cst.FunctionDef | cst.AsyncFunctionDef,
    ) -> cst.FunctionDef | cst.AsyncFunctionDef:
        if self.action is not None or self.non_literal:
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
            if not _function_has_lag_site(original_node, self.name):
                return updated_node

        new_body, action = _patch_function_body_lag_ratio(
            updated_node.body, self.name, self.lag_ratio
        )
        if action == "non_literal":
            self.non_literal = True
            return updated_node
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


def propose_lag_ratio(
    source: str,
    *,
    path: str,
    name: str,
    lag_ratio: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    """Propose setting ``lag_ratio=`` on LaggedStart/AnimationGroup for ``name``."""
    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=lag_ratio,
            dy=0.0,
            source=source,
            error=f"libcst parse failed: {exc}",
        )

    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _LagRatioPatcher(name, lag_ratio, anchor_line)
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=lag_ratio,
            dy=0.0,
            source=source,
            error=f"patch failed: {exc}",
        )

    if patcher.non_literal:
        return _fail_proposal(
            path=path,
            name=name,
            dx=lag_ratio,
            dy=0.0,
            source=source,
            error=f"lag_ratio for {name!r} is not a numeric literal — refusing edit",
        )

    if not patcher.saw_name or patcher.action is None:
        return _fail_proposal(
            path=path,
            name=name,
            dx=lag_ratio,
            dy=0.0,
            source=source,
            error=f"no LaggedStart/AnimationGroup site found for {name!r}",
        )

    proposed = new_module.code
    if proposed == source:
        return _fail_proposal(
            path=path,
            name=name,
            dx=lag_ratio,
            dy=0.0,
            source=source,
            error="patch produced no textual change",
        )

    return _success_proposal(
        path=path,
        name=name,
        dx=lag_ratio,
        dy=0.0,
        source=source,
        proposed=proposed,
        summary=f"set {name} lag_ratio → {_fmt_num(lag_ratio)}",
    )


def propose_lag_ratio_file(
    path: str,
    name: str,
    lag_ratio: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    from pathlib import Path

    source = Path(path).read_text(encoding="utf-8")
    return propose_lag_ratio(
        source, path=path, name=name, lag_ratio=lag_ratio, anchor_line=anchor_line
    )


def propose_literal_kw(
    source: str,
    *,
    path: str,
    name: str,
    attr: str,
    keyword: str,
    value: float,
    anchor_line: int | None = None,
) -> PatchProposal:
    """Propose setting a numeric keyword on the latest ``name.attr(...)`` call."""

    class _LiteralKwPatcher(cst.CSTTransformer):
        METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

        def __init__(self) -> None:
            self.action: str | None = None
            self.saw = False
            self.non_literal = False

        def _maybe_patch(
            self,
            original_node: cst.FunctionDef | cst.AsyncFunctionDef,
            updated_node: cst.FunctionDef | cst.AsyncFunctionDef,
        ) -> cst.FunctionDef | cst.AsyncFunctionDef:
            if self.action is not None or self.non_literal:
                return updated_node

            if anchor_line is not None:
                try:
                    pos = self.get_metadata(
                        cst.metadata.PositionProvider, original_node
                    )
                except Exception:
                    pos = None
                if pos is None or not (
                    pos.start.line <= anchor_line <= pos.end.line
                ):
                    return updated_node

            block = updated_node.body
            if not isinstance(block, cst.IndentedBlock):
                return updated_node

            statements = list(block.body)
            last_idx: int | None = None
            last_call: cst.Call | None = None
            attrs = frozenset({attr})
            for i, stmt in enumerate(statements):
                if not isinstance(stmt, cst.SimpleStatementLine):
                    continue
                if _stmt_is_name_attr_call(stmt, name, attrs):
                    expr = stmt.body[0]
                    assert isinstance(expr, cst.Expr)
                    assert isinstance(expr.value, cst.Call)
                    last_idx = i
                    last_call = expr.value

            if last_idx is None or last_call is None:
                return updated_node

            patched = _set_numeric_kw_or_positional(
                last_call,
                keyword=keyword,
                value=value,
                positional_index=None,
            )
            if patched is None:
                self.non_literal = True
                return updated_node

            old_stmt = statements[last_idx]
            assert isinstance(old_stmt, cst.SimpleStatementLine)
            statements[last_idx] = _stmt_with_replaced_call(
                old_stmt, last_call, patched
            )
            self.saw = True
            self.action = "set"
            return updated_node.with_changes(
                body=block.with_changes(body=statements)
            )

        def leave_FunctionDef(
            self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef
        ) -> cst.FunctionDef:
            return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]

        def leave_AsyncFunctionDef(
            self,
            original_node: cst.AsyncFunctionDef,
            updated_node: cst.AsyncFunctionDef,
        ) -> cst.AsyncFunctionDef:
            return self._maybe_patch(original_node, updated_node)  # type: ignore[return-value]

    try:
        module = cst.parse_module(source)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=value,
            dy=0.0,
            source=source,
            error=f"libcst parse failed: {exc}",
        )

    wrapper = cst.metadata.MetadataWrapper(module)
    patcher = _LiteralKwPatcher()
    try:
        new_module = wrapper.visit(patcher)
    except Exception as exc:  # noqa: BLE001
        return _fail_proposal(
            path=path,
            name=name,
            dx=value,
            dy=0.0,
            source=source,
            error=f"patch failed: {exc}",
        )

    if patcher.non_literal:
        return _fail_proposal(
            path=path,
            name=name,
            dx=value,
            dy=0.0,
            source=source,
            error=f"{keyword} for {name}.{attr}(...) is not a numeric literal",
        )
    if not patcher.saw or patcher.action is None:
        return _fail_proposal(
            path=path,
            name=name,
            dx=value,
            dy=0.0,
            source=source,
            error=f"no {name}.{attr}(...) call found",
        )

    proposed = new_module.code
    if proposed == source:
        return _fail_proposal(
            path=path,
            name=name,
            dx=value,
            dy=0.0,
            source=source,
            error="patch produced no textual change",
        )

    return _success_proposal(
        path=path,
        name=name,
        dx=value,
        dy=0.0,
        source=source,
        proposed=proposed,
        summary=f"set {name}.{attr}({keyword}=) → {_fmt_num(value)}",
    )

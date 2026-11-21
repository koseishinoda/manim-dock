"""Stage-only source transforms: section elision, sibling-scene strip, fast prefixes.

Kept separate from ``snapshot.py`` so AST/string edits stay isolated and testable.
"""

from __future__ import annotations

import ast
import copy
from typing import Callable


def _is_self_method_expr(stmt: ast.stmt, method: str) -> bool:
    if not isinstance(stmt, ast.Expr) or not isinstance(stmt.value, ast.Call):
        return False
    func = stmt.value.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "self"
        and func.attr == method
    )


def _next_section_name(stmt: ast.stmt) -> str | None:
    if not _is_self_method_expr(stmt, "next_section"):
        return None
    call = stmt.value
    assert isinstance(call, ast.Call)
    if (
        call.args
        and isinstance(call.args[0], ast.Constant)
        and isinstance(call.args[0].value, str)
    ):
        return call.args[0].value
    for kw in call.keywords:
        if (
            kw.arg == "name"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            return kw.value.value
    return None


def _find_scene_construct(
    tree: ast.Module, scene_name: str
) -> ast.FunctionDef | None:
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != scene_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == "construct":
                return item
    return None


def discover_focus_sections(source: str, scene_name: str) -> frozenset[str] | None:
    """Section titles marked by ``self.focus()`` / ``focus("…")`` in construct."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if not isinstance(tree, ast.Module):
        return None
    construct = _find_scene_construct(tree, scene_name)
    if construct is None:
        return None

    focus_events: list[tuple[int, tuple[str, ...] | None]] = []
    section_events: list[tuple[int, str]] = []
    for stmt in construct.body:
        lineno = int(getattr(stmt, "lineno", 0) or 0)
        if _is_self_method_expr(stmt, "focus"):
            call = stmt.value
            assert isinstance(call, ast.Call)
            titles = tuple(
                arg.value
                for arg in call.args
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
            )
            if call.args and not titles:
                continue
            focus_events.append((lineno, titles if titles else None))
            continue
        name = _next_section_name(stmt)
        if name is not None:
            section_events.append((lineno, name))

    if not focus_events:
        return None

    names: list[str] = []
    section_index = 0
    for lineno, titles in focus_events:
        if titles is not None:
            names.extend(titles)
            continue
        while (
            section_index < len(section_events)
            and section_events[section_index][0] <= lineno
        ):
            section_index += 1
        if section_index < len(section_events):
            names.append(section_events[section_index][1])
            section_index += 1
    return frozenset(names) if names else None


def section_name_at_line(source: str, scene_name: str, line: int) -> str | None:
    """Enclosing ``next_section`` title for a 1-based construct line."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    if not isinstance(tree, ast.Module):
        return None
    construct = _find_scene_construct(tree, scene_name)
    if construct is None:
        return None
    current: str | None = None
    for stmt in construct.body:
        name = _next_section_name(stmt)
        if name is not None:
            current = name
            continue
    current = None
    for stmt in construct.body:
        name = _next_section_name(stmt)
        if name is None:
            continue
        start = int(getattr(stmt, "lineno", 0) or 0)
        if start <= line:
            current = name
        else:
            break
    return current


def resolve_stage_elide_section(
    source: str,
    scene_name: str,
    active_until_line: int,
    section_hint: str | None = None,
) -> str | None:
    """Section to try body-elision for, or None."""
    section = section_hint or section_name_at_line(
        source, scene_name, active_until_line
    )
    if not section:
        return None
    focused = discover_focus_sections(source, scene_name)
    if focused is not None and section not in focused:
        return None
    return section


def elide_unfocused_section_bodies(
    source: str, scene_name: str, keep_section: str
) -> str:
    """Drop construct bodies of sections other than ``keep_section``."""
    if not keep_section:
        return source
    tree = ast.parse(source)
    if not isinstance(tree, ast.Module):
        return source
    construct = _find_scene_construct(tree, scene_name)
    if construct is None:
        return source

    new_body: list[ast.stmt] = []
    current: str | None = None
    injected_stub = False
    stub = ast.parse("active_panel = VGroup()").body[0]

    for stmt in construct.body:
        name = _next_section_name(stmt)
        if name is not None:
            current = name
            new_body.append(stmt)
            if name == keep_section and not injected_stub:
                new_body.append(copy.deepcopy(stub))
                injected_stub = True
            continue
        if current is None or current == keep_section:
            new_body.append(stmt)
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            new_body.append(stmt)

    if not injected_stub:
        return source

    construct.body = new_body
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def strip_other_scene_classes(source: str, scene_name: str) -> str:
    """Drop sibling ``Scene*`` class bodies from a temp Stage module."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source
    if not isinstance(tree, ast.Module):
        return source
    new_body: list[ast.stmt] = []
    dropped = False
    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name != scene_name
            and (
                node.name.startswith("Scene")
                or any(
                    isinstance(base, ast.Name) and base.id.endswith("Scene")
                    for base in node.bases
                )
            )
        ):
            dropped = True
            continue
        new_body.append(node)
    if not dropped:
        return source
    tree.body = new_body
    ast.fix_missing_locations(tree)
    return ast.unparse(tree)


def _is_construct(node: ast.AST) -> bool:
    return isinstance(node, ast.FunctionDef) and node.name == "construct"


def construct_prefix_index(
    source: str, scene_name: str
) -> tuple[str, list[tuple[int, int, str]]] | str:
    """Parse once → ``(header, [(start, end, dump), ...])`` or error tag."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return "SYNTAX_ERROR:" + str(exc)
    if not isinstance(tree, ast.Module):
        return "NOT_MODULE"

    header_bits: list[str] = [f"scene={scene_name}"]
    construct: ast.FunctionDef | None = None
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            header_bits.append(ast.dump(node, include_attributes=False))
        elif isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Assign, ast.AnnAssign)
        ):
            header_bits.append(ast.dump(node, include_attributes=False))
        elif isinstance(node, ast.ClassDef) and node.name == scene_name:
            for item in node.body:
                if _is_construct(item):
                    construct = item
                    break
            if construct is None:
                header_bits.append(ast.dump(node, include_attributes=False))
                return "\n".join(header_bits), []
            for item in node.body:
                if item is construct:
                    continue
                header_bits.append(
                    "cls:" + ast.dump(item, include_attributes=False)
                )

    if construct is None:
        return "\n".join(header_bits), []

    stmts: list[tuple[int, int, str]] = []
    for stmt in construct.body:
        start_ln = int(getattr(stmt, "lineno", 0) or 0)
        end_ln = int(
            getattr(stmt, "end_lineno", None) or getattr(stmt, "lineno", 0) or 0
        )
        stmts.append(
            (start_ln, end_ln, ast.dump(stmt, include_attributes=False))
        )
    return "\n".join(header_bits), stmts


def prefix_from_index(
    header: str, stmts: list[tuple[int, int, str]], active_until_line: int
) -> str:
    bits = [header, f"until={active_until_line}"]
    if active_until_line < 1:
        return "\n".join(bits)
    for start_ln, end_ln, dump in stmts:
        if end_ln <= 0:
            continue
        if end_ln <= active_until_line:
            bits.append(dump)
            continue
        if start_ln <= active_until_line <= end_ln:
            bits.append(dump)
        break
    return "\n".join(bits)


def construct_prefix_canonical_many(
    source: str, scene_name: str, lines: list[int]
) -> dict[int, str]:
    """Batch prefix strings for many Stage lines (one parse + one dump pass)."""
    indexed = construct_prefix_index(source, scene_name)
    if isinstance(indexed, str):
        return {line: indexed for line in lines}
    header, stmts = indexed
    return {line: prefix_from_index(header, stmts, line) for line in lines}


def prepare_stage_source(
    source: str,
    scene_name: str,
    active_until_line: int,
    *,
    inject_early_exit: Callable[[str, int], str],
    elide_section: str | None,
) -> str:
    """Early-exit + optional section elision + strip sibling scenes."""
    transformed = inject_early_exit(source, active_until_line)
    if elide_section:
        transformed = elide_unfocused_section_bodies(
            transformed, scene_name, elide_section
        )
    return strip_other_scene_classes(transformed, scene_name)


def apply_animation_end_state(animation: object, scene: object) -> None:
    """Jump a compiled animation to its end state without ``begin()`` copies."""
    try:
        from manim.animation.animation import Wait  # type: ignore[import-not-found]
        from manim.animation.composition import (  # type: ignore[import-not-found]
            AnimationGroup,
            Succession,
        )
        from manim.animation.creation import (  # type: ignore[import-not-found]
            Create,
            DrawBorderThenFill,
            Uncreate,
            Unwrite,
            Write,
        )
        from manim.animation.fading import FadeIn, FadeOut  # type: ignore[import-not-found]
        from manim.animation.indication import Indicate  # type: ignore[import-not-found]
        from manim.animation.transform import (  # type: ignore[import-not-found]
            ApplyMethod,
            Transform,
            _MethodAnimation,
        )
    except Exception:
        animation.begin()  # type: ignore[attr-defined]
        animation.finish()  # type: ignore[attr-defined]
        animation.clean_up_from_scene(scene)  # type: ignore[attr-defined]
        return

    if isinstance(animation, AnimationGroup):
        for sub in animation.animations:
            apply_animation_end_state(sub, scene)
        if getattr(animation, "suspend_mobject_updating", False):
            animation.group.resume_updating()
        return
    if isinstance(animation, Succession):
        for sub in animation.animations:
            apply_animation_end_state(sub, scene)
        return
    if isinstance(animation, Wait):
        return

    animation._setup_scene(scene)  # type: ignore[attr-defined]

    if isinstance(animation, Indicate):
        return
    if isinstance(animation, _MethodAnimation):
        for item in animation.methods:
            item.method.__func__(animation.mobject, *item.args, **item.kwargs)
        return
    if isinstance(animation, ApplyMethod):
        method = animation.method
        args = list(animation.method_args)
        if args and isinstance(args[-1], dict):
            kwargs = args.pop()
        else:
            kwargs = {}
        method.__func__(animation.mobject, *args, **kwargs)
        return
    if isinstance(animation, FadeIn):
        return
    if isinstance(animation, FadeOut):
        scene.remove(animation.mobject)  # type: ignore[attr-defined]
        return
    if isinstance(animation, (Write, Create, DrawBorderThenFill)):
        return
    if isinstance(animation, (Uncreate, Unwrite)):
        scene.remove(animation.mobject)  # type: ignore[attr-defined]
        return
    if isinstance(animation, Transform):
        target = animation.create_target()
        animation.target_mobject = target
        if getattr(animation, "replace_mobject_with_target_in_scene", False):
            scene.replace(animation.mobject, target)  # type: ignore[attr-defined]
        else:
            animation.mobject.become(target)
        return

    animation.begin()  # type: ignore[attr-defined]
    animation.finish()  # type: ignore[attr-defined]
    animation.clean_up_from_scene(scene)  # type: ignore[attr-defined]


class stage_fast_play_patches:
    """Context manager: patch Cairo ``play`` for Stage last-frame capture."""

    def __enter__(self) -> stage_fast_play_patches:
        try:
            from manim.renderer.cairo_renderer import (  # type: ignore[import-not-found]
                CairoRenderer,
            )
        except Exception:
            self._original = None
            return self

        self._renderer = CairoRenderer
        self._original = CairoRenderer.play

        def play_fast(self_renderer: object, scene: object, *args: object, **kwargs: object) -> None:
            self_renderer.skip_animations = self_renderer._original_skipping_status  # type: ignore[attr-defined]
            self_renderer.update_skipping_status()  # type: ignore[attr-defined]
            result = scene.compile_animation_data(*args, **kwargs)  # type: ignore[attr-defined]
            self_renderer.file_writer.add_partial_movie_file(None)  # type: ignore[attr-defined]
            self_renderer.animations_hashes.append(None)  # type: ignore[attr-defined]
            if result is None:
                self_renderer.time += getattr(scene, "duration", 0) or 0  # type: ignore[attr-defined]
                self_renderer.num_plays += 1  # type: ignore[attr-defined]
                return
            self_renderer.time += scene.duration  # type: ignore[attr-defined]
            assert scene.animations is not None  # type: ignore[attr-defined]
            for anim in scene.animations:  # type: ignore[attr-defined]
                apply_animation_end_state(anim, scene)
            scene.update_mobjects(0)  # type: ignore[attr-defined]
            self_renderer.static_image = None  # type: ignore[attr-defined]
            self_renderer.num_plays += 1  # type: ignore[attr-defined]

        CairoRenderer.play = play_fast  # type: ignore[method-assign]
        return self

    def __exit__(self, *args: object) -> None:
        if getattr(self, "_original", None) is not None:
            self._renderer.play = self._original  # type: ignore[method-assign]

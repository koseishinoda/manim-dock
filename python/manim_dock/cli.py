"""CLI entrypoints for local development and the extension."""

from __future__ import annotations

import argparse
import json
import sys

from manim_dock.doctor import run_doctor
from manim_dock.extract import propose_extract_method_files
from manim_dock.layout import parse_file_layout
from manim_dock.library_catalog import list_library_helpers
from manim_dock.outline import parse_file
from manim_dock.align import compute_align_deltas
from manim_dock.patch_layout import (
    propose_buff_file,
    propose_font_size_file,
    propose_lag_ratio_file,
    propose_scale_file,
    propose_shift_file,
)
from manim_dock.patch_insert import (
    propose_insert_play_file,
    propose_insert_wait_file,
)
from manim_dock.patch_timing import (
    propose_duration_file,
    propose_reorder_file,
    propose_section_reorder_file,
)
from manim_dock.render import render_scene
from manim_dock.scaffold import scaffold_example
from manim_dock.scrub import scrub_layout
from manim_dock.server import serve
from manim_dock.timeline import parse_file_timeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manim-dock", description="Manim Dock sidecar")
    sub = parser.add_subparsers(dest="command", required=True)

    outline_p = sub.add_parser("outline", help="Print scene outline as JSON")
    outline_p.add_argument("path", help="Path to a .py scene file")

    layout_p = sub.add_parser("layout", help="Print Stage layout view model as JSON")
    layout_p.add_argument("path", help="Path to a .py scene file")
    layout_p.add_argument("scene", help="Scene class name")

    shift_p = sub.add_parser("propose-shift", help="Propose a relative shift patch (no write)")
    shift_p.add_argument("path", help="Path to a .py scene file")
    shift_p.add_argument("name", help="Local mobject variable name")
    shift_p.add_argument("--dx", type=float, required=True, help="Delta x in Manim units")
    shift_p.add_argument("--dy", type=float, required=True, help="Delta y in Manim units")
    shift_p.add_argument(
        "--anchor-line",
        type=int,
        default=None,
        help="1-based line inside the owning function (scopes the patch)",
    )

    timeline_p = sub.add_parser("timeline", help="Print Timeline view model as JSON")
    timeline_p.add_argument("path", help="Path to a .py scene file")
    timeline_p.add_argument("scene", help="Scene class name")

    dur_p = sub.add_parser(
        "propose-duration", help="Propose a wait/run_time patch (no write)"
    )
    dur_p.add_argument("path", help="Path to a .py scene file")
    dur_p.add_argument("kind", choices=["play", "wait"], help="Event kind")
    dur_p.add_argument("line", type=int, help="1-based line of the self.play/wait call")
    dur_p.add_argument("--duration", type=float, required=True, help="New duration seconds")

    buff_p = sub.add_parser(
        "propose-buff", help="Propose a buff= patch on arrange/next_to/SurroundingRectangle"
    )
    buff_p.add_argument("path", help="Path to a .py scene file")
    buff_p.add_argument("name", help="Local mobject variable name")
    buff_p.add_argument("--buff", type=float, required=True, help="New buff value")
    buff_p.add_argument(
        "--anchor-line",
        type=int,
        default=None,
        help="1-based line inside the owning function (scopes the patch)",
    )

    scale_p = sub.add_parser(
        "propose-scale", help="Propose inserting name.scale(factor) (no write)"
    )
    scale_p.add_argument("path", help="Path to a .py scene file")
    scale_p.add_argument("name", help="Local mobject variable name")
    scale_p.add_argument("--factor", type=float, required=True, help="Scale factor (>0, ≠1)")
    scale_p.add_argument(
        "--anchor-line",
        type=int,
        default=None,
        help="1-based line inside the owning function (scopes the patch)",
    )

    font_p = sub.add_parser(
        "propose-font-size", help="Propose a font_size= patch on Text/MathTex/..."
    )
    font_p.add_argument("path", help="Path to a .py scene file")
    font_p.add_argument("name", help="Local mobject variable name")
    font_p.add_argument(
        "--font-size", type=float, required=True, help="New font_size value"
    )
    font_p.add_argument(
        "--anchor-line",
        type=int,
        default=None,
        help="1-based line inside the owning function (scopes the patch)",
    )

    lag_p = sub.add_parser(
        "propose-lag-ratio",
        help="Propose a lag_ratio= patch on LaggedStart/AnimationGroup",
    )
    lag_p.add_argument("path", help="Path to a .py scene file")
    lag_p.add_argument("name", help="Local mobject variable name referenced by the lag")
    lag_p.add_argument(
        "--lag-ratio", type=float, required=True, help="New lag_ratio value"
    )
    lag_p.add_argument(
        "--anchor-line",
        type=int,
        default=None,
        help="1-based line inside the owning function (scopes the patch)",
    )

    scrub_p = sub.add_parser(
        "scrub-layout", help="Approximate Stage positions up to a source line"
    )
    scrub_p.add_argument("path", help="Path to a .py scene file")
    scrub_p.add_argument("scene", help="Scene class name")
    scrub_p.add_argument(
        "active_until_line",
        type=int,
        help="1-based line — include layout calls ending at/before this line",
    )

    align_p = sub.add_parser(
        "align-deltas", help="Compute align/distribute dx/dy for Stage items (JSON)"
    )
    align_p.add_argument(
        "mode",
        choices=[
            "left",
            "right",
            "center_x",
            "top",
            "bottom",
            "center_y",
            "distribute_x",
            "distribute_y",
        ],
        help="Align or distribute mode",
    )
    align_p.add_argument(
        "items_json",
        help='JSON list of {"name","x","y"} objects',
    )

    reorder_p = sub.add_parser(
        "propose-reorder",
        help="Propose swapping two adjacent self.play/self.wait statements",
    )
    reorder_p.add_argument("path", help="Path to a .py scene file")
    reorder_p.add_argument("line_a", type=int, help="1-based start line of first statement")
    reorder_p.add_argument("line_b", type=int, help="1-based start line of second statement")

    section_reorder_p = sub.add_parser(
        "propose-section-reorder",
        help="Propose swapping two adjacent next_section blocks in construct()",
    )
    section_reorder_p.add_argument("path", help="Path to a .py scene file")
    section_reorder_p.add_argument(
        "line_a", type=int, help="1-based start line of first next_section"
    )
    section_reorder_p.add_argument(
        "line_b", type=int, help="1-based start line of second next_section"
    )

    insert_wait_p = sub.add_parser(
        "propose-insert-wait",
        help="Propose inserting self.wait(...) after a statement (no write)",
    )
    insert_wait_p.add_argument("path", help="Path to a .py scene file")
    insert_wait_p.add_argument(
        "after_line",
        type=int,
        help="1-based start line of the statement to insert after",
    )
    insert_wait_p.add_argument(
        "--duration",
        type=float,
        default=0.5,
        help="Wait duration seconds (default: 0.5)",
    )

    insert_play_p = sub.add_parser(
        "propose-insert-play",
        help="Propose inserting self.play(...) scaffold after a statement (no write)",
    )
    insert_play_p.add_argument("path", help="Path to a .py scene file")
    insert_play_p.add_argument(
        "after_line",
        type=int,
        help="1-based start line of the statement to insert after",
    )
    insert_play_p.add_argument(
        "--anim-code",
        default="FadeIn(Dot())",
        help='Animation expression inside self.play(...) (default: FadeIn(Dot()))',
    )

    extract_p = sub.add_parser(
        "extract-method", help="Propose extracting a Scene method to a library module"
    )
    extract_p.add_argument("path", help="Path to a .py scene file")
    extract_p.add_argument("scene", help="Scene class name")
    extract_p.add_argument("method", help="Method name to extract")
    extract_p.add_argument("library", help="Target library .py path")

    render_p = sub.add_parser("render", help="Render a scene with ManimCE (default -ql)")
    render_p.add_argument("path", help="Path to a .py scene file")
    render_p.add_argument("scene", help="Scene class name")
    render_p.add_argument(
        "--quality",
        default="l",
        help="Quality letter or name: l/m/h/k (default: l)",
    )
    render_p.add_argument(
        "--save-sections",
        action="store_true",
        help="Pass --save_sections to manim (chapterized outputs)",
    )
    render_p.add_argument(
        "--skip-until-section",
        default=None,
        metavar="NAME",
        help="Skip animations before this next_section name (temp copy; user file untouched)",
    )
    render_p.add_argument(
        "--method",
        default=None,
        metavar="NAME",
        help="Render only by rewriting construct to self.NAME() (temp copy; user file untouched)",
    )

    lib_p = sub.add_parser(
        "library-catalog",
        help="List plain helper functions from a library .py for insert snippets",
    )
    lib_p.add_argument("path", help="Path to a library .py file")

    scaffold_p = sub.add_parser(
        "scaffold-example",
        help="Copy examples/minimal_lesson into DEST",
    )
    scaffold_p.add_argument("dest", help="Destination directory")

    sub.add_parser("doctor", help="Probe Python / manim / LaTeX / ffmpeg")
    sub.add_parser("serve", help="Stdio JSON line protocol for the VS Code host")

    args = parser.parse_args(argv)

    if args.command == "outline":
        data = parse_file(args.path).to_dict()
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if data.get("errors") else 0

    if args.command == "layout":
        data = parse_file_layout(args.path, args.scene).to_dict()
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if data.get("errors") else 0

    if args.command == "propose-shift":
        data = propose_shift_file(
            args.path, args.name, args.dx, args.dy, args.anchor_line
        ).to_dict()
        # Keep payload small in CLI: drop full sources unless failed.
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "timeline":
        data = parse_file_timeline(args.path, args.scene).to_dict()
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if data.get("errors") else 0

    if args.command == "propose-duration":
        data = propose_duration_file(
            args.path, args.kind, args.line, args.duration
        ).to_dict()
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "propose-buff":
        data = propose_buff_file(
            args.path, args.name, args.buff, args.anchor_line
        ).to_dict()
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "propose-scale":
        data = propose_scale_file(
            args.path, args.name, args.factor, args.anchor_line
        ).to_dict()
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "propose-font-size":
        data = propose_font_size_file(
            args.path, args.name, args.font_size, args.anchor_line
        ).to_dict()
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "propose-lag-ratio":
        data = propose_lag_ratio_file(
            args.path, args.name, args.lag_ratio, args.anchor_line
        ).to_dict()
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "scrub-layout":
        data = scrub_layout(args.path, args.scene, args.active_until_line)
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if data.get("errors") else 0

    if args.command == "align-deltas":
        try:
            items = json.loads(args.items_json)
        except json.JSONDecodeError as exc:
            json.dump({"error": f"invalid items JSON: {exc}"}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 1
        if not isinstance(items, list):
            json.dump({"error": "items_json must be a JSON list"}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 1
        data = {"deltas": compute_align_deltas(items, args.mode)}
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.command == "propose-reorder":
        data = propose_reorder_file(args.path, args.line_a, args.line_b).to_dict()
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "propose-section-reorder":
        data = propose_section_reorder_file(
            args.path, args.line_a, args.line_b
        ).to_dict()
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "propose-insert-wait":
        data = propose_insert_wait_file(
            args.path, args.after_line, args.duration
        ).to_dict()
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "propose-insert-play":
        data = propose_insert_play_file(
            args.path, args.after_line, args.anim_code
        ).to_dict()
        if data.get("ok"):
            data = {k: v for k, v in data.items() if k not in {"original", "proposed"}}
            data["proposed_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "extract-method":
        data = propose_extract_method_files(
            args.path, args.scene, args.method, args.library
        ).to_dict()
        if data.get("ok"):
            data = {
                k: v
                for k, v in data.items()
                if k
                not in {
                    "scene_original",
                    "scene_proposed",
                    "library_original",
                    "library_proposed",
                }
            }
            data["sources_omitted"] = True
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "render":
        result = render_scene(
            args.path,
            args.scene,
            quality=args.quality,
            save_sections=bool(args.save_sections),
            skip_until_section=args.skip_until_section,
            method=args.method,
        )
        json.dump(result.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if result.ok else 1

    if args.command == "library-catalog":
        try:
            helpers = list_library_helpers(args.path)
        except (OSError, ValueError) as exc:
            json.dump({"ok": False, "error": str(exc)}, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return 1
        json.dump({"ok": True, "helpers": helpers}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    if args.command == "scaffold-example":
        data = scaffold_example(args.dest)
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if data.get("ok") else 1

    if args.command == "doctor":
        probes = run_doctor()
        json.dump({"probes": [p.to_dict() for p in probes]}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if all(p.ok for p in probes) else 1

    if args.command == "serve":
        serve()
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI entrypoints for local development and the extension."""

from __future__ import annotations

import argparse
import json
import sys

from manim_dock.extract import propose_extract_method_files
from manim_dock.library_catalog import list_library_helpers
from manim_dock.outline import parse_file
from manim_dock.patch_timing import (
    propose_duration_file,
    propose_reorder_file,
    propose_section_reorder_file,
)
from manim_dock.render import render_scene
from manim_dock.scaffold import scaffold_example
from manim_dock.server import serve
from manim_dock.snapshot import snapshot_at_line
from manim_dock.timeline import parse_file_timeline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manim-dock", description="Manim Dock sidecar")
    sub = parser.add_subparsers(dest="command", required=True)

    outline_p = sub.add_parser("outline", help="Print scene outline as JSON")
    outline_p.add_argument("path", help="Path to a .py scene file")

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

    extract_p = sub.add_parser(
        "extract-method", help="Propose extracting a Scene method to a library module"
    )
    extract_p.add_argument("path", help="Path to a .py scene file")
    extract_p.add_argument("scene", help="Scene class name")
    extract_p.add_argument("method", help="Method name to extract")
    extract_p.add_argument("library", help="Target library .py path")

    snap_p = sub.add_parser(
        "snapshot",
        help="Capture a ManimCE still PNG at a source line (Stage fidelity)",
    )
    snap_p.add_argument("path", help="Path to a .py scene file")
    snap_p.add_argument("scene", help="Scene class name")
    snap_p.add_argument(
        "active_until_line",
        type=int,
        help="1-based line — run construct through this line, then stop",
    )
    snap_p.add_argument(
        "--quality",
        default="l",
        help="Quality letter or name: l/m/h/k (default: l)",
    )
    snap_p.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Subprocess timeout seconds (default: 60)",
    )

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

    sub.add_parser("serve", help="Stdio JSON line protocol for the VS Code host")

    args = parser.parse_args(argv)

    if args.command == "outline":
        data = parse_file(args.path).to_dict()
        json.dump(data, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 1 if data.get("errors") else 0

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

    if args.command == "snapshot":
        result = snapshot_at_line(
            args.path,
            args.scene,
            args.active_until_line,
            quality=args.quality,
            timeout=args.timeout,
        )
        json.dump(result.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if result.ok else 1

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

    if args.command == "serve":
        serve()
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())

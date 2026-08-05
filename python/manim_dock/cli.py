"""CLI entrypoints for local development and the extension."""

from __future__ import annotations

import argparse
import json
import sys

from manim_dock.doctor import run_doctor
from manim_dock.layout import parse_file_layout
from manim_dock.outline import parse_file
from manim_dock.patch_layout import propose_shift_file
from manim_dock.patch_timing import propose_duration_file
from manim_dock.render import render_scene
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

    render_p = sub.add_parser("render", help="Render a scene with ManimCE (default -ql)")
    render_p.add_argument("path", help="Path to a .py scene file")
    render_p.add_argument("scene", help="Scene class name")
    render_p.add_argument(
        "--quality",
        default="l",
        help="Quality letter or name: l/m/h/k (default: l)",
    )

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

    if args.command == "render":
        result = render_scene(args.path, args.scene, quality=args.quality)
        json.dump(result.to_dict(), sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0 if result.ok else 1

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

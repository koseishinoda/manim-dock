"""CLI entrypoints for local development and the extension."""

from __future__ import annotations

import argparse
import json
import sys

from manim_dock.doctor import run_doctor
from manim_dock.outline import parse_file
from manim_dock.render import render_scene
from manim_dock.server import serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manim-dock", description="Manim Dock sidecar")
    sub = parser.add_subparsers(dest="command", required=True)

    outline_p = sub.add_parser("outline", help="Print scene outline as JSON")
    outline_p.add_argument("path", help="Path to a .py scene file")

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

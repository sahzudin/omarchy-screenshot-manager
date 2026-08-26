#!/usr/bin/env python3
"""Helper for the Omarchy Screenshot Manager plugin.

Lists screenshots taken by `omarchy capture screenshot`, moves them to the
desktop trash, and copies them to the clipboard as PNG data. Runs
unprivileged — screenshots are user-owned files in the Pictures directory.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from typing import Sequence


class ScreenshotError(RuntimeError):
    pass


SCREENSHOT_NAME_RE = re.compile(r"^screenshot-.*\.png$", re.IGNORECASE)
MAX_LIST_COUNT = 200


def parse_user_dirs() -> dict[str, str]:
    values: dict[str, str] = {}
    path = os.path.expanduser("~/.config/user-dirs.dirs")
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, raw = line.partition("=")
                key = key.strip()
                raw = raw.strip().strip('"')
                if raw.startswith("$HOME"):
                    raw = os.path.expanduser("~") + raw[len("$HOME"):]
                values[key] = raw
    except OSError:
        pass
    return values


def screenshots_dir() -> str:
    env_dir = os.environ.get("OMARCHY_SCREENSHOT_DIR")
    if env_dir and env_dir.strip():
        return os.path.abspath(os.path.expanduser(env_dir.strip()))
    xdg_pictures = parse_user_dirs().get("XDG_PICTURES_DIR")
    if xdg_pictures and xdg_pictures.strip():
        return os.path.abspath(os.path.expanduser(xdg_pictures.strip()))
    return os.path.abspath(os.path.expanduser("~/Pictures"))


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{size}B"


def list_screenshots() -> dict[str, object]:
    directory = screenshots_dir()
    matches = []
    for entry in glob.glob(os.path.join(directory, "screenshot-*.png")):
        if not SCREENSHOT_NAME_RE.match(os.path.basename(entry)):
            continue
        try:
            stat = os.stat(entry)
        except OSError:
            continue
        matches.append(
            {
                "path": entry,
                "name": os.path.basename(entry),
                "size": stat.st_size,
                "humanSize": human_size(stat.st_size),
                "mtimeIso": datetime.fromtimestamp(stat.st_mtime).astimezone().isoformat(timespec="seconds"),
            }
        )

    matches.sort(key=lambda item: item["mtimeIso"], reverse=True)
    total = len(matches)
    return {
        "dir": directory,
        "dirName": os.path.basename(directory),
        "count": min(total, MAX_LIST_COUNT),
        "total": total,
        "screenshots": matches[:MAX_LIST_COUNT],
    }


def validate_screenshot_path(path: str) -> str:
    if not path or not os.path.isabs(path):
        raise ScreenshotError("Screenshot path must be absolute")
    if not SCREENSHOT_NAME_RE.match(os.path.basename(path)):
        raise ScreenshotError("Only screenshots taken by omarchy capture can be managed here")
    if not os.path.isfile(path):
        raise ScreenshotError("Screenshot file does not exist")

    directory = screenshots_dir()
    try:
        real_path = os.path.realpath(path)
        real_dir = os.path.realpath(directory)
    except OSError as error:
        raise ScreenshotError("Could not resolve screenshot path") from error
    if real_path != real_dir and not real_path.startswith(real_dir + os.sep):
        raise ScreenshotError("Screenshot is outside the screenshots directory")
    return real_path


def run_checked(
    arguments: Sequence[str],
    *,
    input_bytes: bytes | None = None,
    quiet: bool = False,
) -> None:
    # `quiet` is required for wl-copy: it forks a background daemon that
    # owns the Wayland selection, and if we give it pipes the daemon inherits
    # them, so subprocess.run blocks forever waiting for EOF. Redirecting to
    # devnull lets the parent return while the daemon keeps serving the
    # clipboard.
    stdout = subprocess.DEVNULL if quiet else subprocess.PIPE
    stderr = subprocess.DEVNULL if quiet else subprocess.PIPE
    result = subprocess.run(
        list(arguments),
        input=input_bytes,
        stdout=stdout,
        stderr=stderr,
    )
    if result.returncode != 0:
        detail = ""
        if not quiet and result.stderr is not None:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ScreenshotError(detail or "command failed")


def trash(path: str) -> dict[str, object]:
    real_path = validate_screenshot_path(path)
    if shutil.which("gio") is None:
        raise ScreenshotError("gio is not installed")
    run_checked(["gio", "trash", real_path])
    return {"trashed": {"path": real_path}}


def clear_screenshots() -> dict[str, object]:
    if shutil.which("gio") is None:
        raise ScreenshotError("gio is not installed")
    trashed: list[str] = []
    for entry in glob.glob(os.path.join(screenshots_dir(), "screenshot-*.png")):
        if not SCREENSHOT_NAME_RE.match(os.path.basename(entry)):
            continue
        try:
            real_path = validate_screenshot_path(entry)
        except ScreenshotError:
            continue
        run_checked(["gio", "trash", real_path])
        trashed.append(real_path)
    return {"trashed": trashed}


def copy(path: str) -> dict[str, object]:
    real_path = validate_screenshot_path(path)
    if shutil.which("wl-copy") is None:
        raise ScreenshotError("wl-copy is not installed")
    try:
        with open(real_path, "rb") as handle:
            content = handle.read()
    except OSError as error:
        raise ScreenshotError("Could not read screenshot") from error
    run_checked(["wl-copy", "-t", "image/png"], input_bytes=content, quiet=True)
    return {"copied": {"path": real_path}}


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        description="List, trash, and copy Omarchy screenshots"
    )
    subcommands = command_parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("list")

    subcommands.add_parser("clear")

    trash_parser = subcommands.add_parser("trash")
    trash_parser.add_argument("path")

    copy_parser = subcommands.add_parser("copy")
    copy_parser.add_argument("path")
    return command_parser


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.command == "list":
        result = list_screenshots()
    elif args.command == "clear":
        result = clear_screenshots()
    elif args.command == "trash":
        result = trash(args.path)
    else:
        result = copy(args.path)

    json.dump(result, sys.stdout, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ScreenshotError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
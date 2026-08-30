#!/usr/bin/env python3
"""Bounded, symlink-safe helper for the Omarchy Screenshot Manager plugin."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator, Sequence


class ScreenshotError(RuntimeError):
    pass


SCREENSHOT_NAME_RE = re.compile(r"^screenshot-.*\.png$", re.IGNORECASE)
CACHE_NAME_RE = re.compile(r"^[0-9a-f]{64}\.png$")
MAX_LIST_COUNT = 200
MAX_FILE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_WIDTH = 16_384
MAX_IMAGE_HEIGHT = 16_384
MAX_IMAGE_PIXELS = 40_000_000
PNG_HEADER_BYTES = 24
COPY_CHUNK_BYTES = 64 * 1024
MAX_USER_DIRS_BYTES = 64 * 1024
SEEN_FILE_NAME = "seen"
MAX_SEEN_BYTES = 32


@dataclass(frozen=True)
class OpenScreenshot:
    fd: int
    path: str
    name: str
    size: int
    mtime_ns: int
    device: int
    inode: int
    width: int
    height: int


def parse_user_dirs() -> dict[str, str]:
    values: dict[str, str] = {}
    path = os.path.expanduser("~/.config/user-dirs.dirs")
    try:
        fd = os.open(
            path,
            os.O_RDONLY
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_NONBLOCK", 0),
        )
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_USER_DIRS_BYTES:
            return values
        content = os.read(fd, MAX_USER_DIRS_BYTES + 1)
    except OSError:
        return values
    finally:
        if "fd" in locals():
            os.close(fd)
    if len(content) > MAX_USER_DIRS_BYTES:
        return values
    for line in content.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, raw = line.partition("=")
        key = key.strip()
        raw = raw.strip().strip('"')
        if raw.startswith("$HOME"):
            raw = os.path.expanduser("~") + raw[len("$HOME"):]
        values[key] = raw
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


def _directory_flags() -> int:
    return os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_DIRECTORY", 0)


def _file_flags() -> int:
    return (
        os.O_RDONLY
        | os.O_CLOEXEC
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _open_directory(directory: str) -> int:
    try:
        return os.open(directory, _directory_flags())
    except OSError as error:
        raise ScreenshotError("Could not open screenshots directory") from error


def _png_dimensions(fd: int) -> tuple[int, int]:
    try:
        header = os.pread(fd, PNG_HEADER_BYTES, 0)
    except OSError as error:
        raise ScreenshotError("Could not read screenshot header") from error
    if (
        len(header) != PNG_HEADER_BYTES
        or header[:8] != b"\x89PNG\r\n\x1a\n"
        or header[8:12] != b"\x00\x00\x00\r"
        or header[12:16] != b"IHDR"
    ):
        raise ScreenshotError("Screenshot is not a valid PNG image")
    width, height = struct.unpack(">II", header[16:24])
    if (
        width == 0
        or height == 0
        or width > MAX_IMAGE_WIDTH
        or height > MAX_IMAGE_HEIGHT
        or width * height > MAX_IMAGE_PIXELS
    ):
        raise ScreenshotError("Screenshot dimensions exceed the safe preview limit")
    return width, height


def _open_screenshot_at(directory_fd: int, directory: str, name: str) -> OpenScreenshot:
    if not SCREENSHOT_NAME_RE.fullmatch(name) or os.path.basename(name) != name:
        raise ScreenshotError("Only screenshots taken by omarchy capture can be managed here")
    try:
        name.encode("utf-8")
        fd = os.open(name, _file_flags(), dir_fd=directory_fd)
    except (OSError, UnicodeError) as error:
        raise ScreenshotError("Could not safely open screenshot") from error
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode):
            raise ScreenshotError("Screenshot must be a regular file")
        if metadata.st_size > MAX_FILE_BYTES:
            raise ScreenshotError("Screenshot exceeds the 32 MB size limit")
        if metadata.st_size < PNG_HEADER_BYTES:
            raise ScreenshotError("Screenshot is not a valid PNG image")
        width, height = _png_dimensions(fd)
        return OpenScreenshot(
            fd=fd,
            path=os.path.join(directory, name),
            name=name,
            size=metadata.st_size,
            mtime_ns=metadata.st_mtime_ns,
            device=metadata.st_dev,
            inode=metadata.st_ino,
            width=width,
            height=height,
        )
    except Exception:
        os.close(fd)
        raise


@contextlib.contextmanager
def open_screenshot(path: str) -> Iterator[OpenScreenshot]:
    directory = screenshots_dir()
    if not path or not os.path.isabs(path) or os.path.dirname(path) != directory:
        raise ScreenshotError("Screenshot path must be directly inside the screenshots directory")
    directory_fd = _open_directory(directory)
    screenshot: OpenScreenshot | None = None
    try:
        screenshot = _open_screenshot_at(directory_fd, directory, os.path.basename(path))
        yield screenshot
    finally:
        if screenshot is not None:
            os.close(screenshot.fd)
        os.close(directory_fd)


def validate_screenshot_path(path: str) -> str:
    with open_screenshot(path) as screenshot:
        return screenshot.path


def _runtime_directory() -> str:
    candidates = [os.environ.get("XDG_RUNTIME_DIR"), f"/run/user/{os.getuid()}"]
    for candidate in candidates:
        if not candidate or not os.path.isabs(candidate):
            continue
        try:
            metadata = os.stat(candidate, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == os.getuid():
            return candidate
    return tempfile.gettempdir()


def _open_cache_directory() -> tuple[int, str]:
    path = os.path.join(_runtime_directory(), f"omarchy-screenshot-manager-{os.getuid()}")
    try:
        os.mkdir(path, 0o700)
    except FileExistsError:
        pass
    except OSError as error:
        raise ScreenshotError("Could not create the preview cache") from error
    fd: int | None = None
    try:
        fd = os.open(path, _directory_flags() | getattr(os, "O_NOFOLLOW", 0))
        metadata = os.fstat(fd)
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise ScreenshotError("Preview cache permissions are unsafe")
        return fd, path
    except Exception:
        if fd is not None:
            os.close(fd)
        raise


def _cache_key(screenshot: OpenScreenshot) -> str:
    identity = "\0".join(
        (
            screenshot.path,
            str(screenshot.device),
            str(screenshot.inode),
            str(screenshot.size),
            str(screenshot.mtime_ns),
            str(screenshot.width),
            str(screenshot.height),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".png"


def _same_file(screenshot: OpenScreenshot, metadata: os.stat_result) -> bool:
    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_dev == screenshot.device
        and metadata.st_ino == screenshot.inode
        and metadata.st_size == screenshot.size
        and metadata.st_mtime_ns == screenshot.mtime_ns
    )


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise ScreenshotError("Could not write preview cache")
        view = view[written:]


def _validate_cached_file(cache_fd: int, name: str, expected: OpenScreenshot) -> bool:
    try:
        fd = os.open(name, _file_flags(), dir_fd=cache_fd)
    except OSError:
        return False
    try:
        metadata = os.fstat(fd)
        return (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_size == expected.size
            and metadata.st_size <= MAX_FILE_BYTES
            and _png_dimensions(fd) == (expected.width, expected.height)
        )
    except (OSError, ScreenshotError):
        return False
    finally:
        os.close(fd)


def _materialize_preview(cache_fd: int, cache_path: str, screenshot: OpenScreenshot) -> str:
    cache_name = _cache_key(screenshot)
    if _validate_cached_file(cache_fd, cache_name, screenshot):
        return os.path.join(cache_path, cache_name)

    temporary_name = f".{cache_name}.{os.getpid()}.tmp"
    temporary_fd: int | None = None
    try:
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=cache_fd,
        )
        os.lseek(screenshot.fd, 0, os.SEEK_SET)
        copied = 0
        while True:
            chunk = os.read(screenshot.fd, COPY_CHUNK_BYTES)
            if not chunk:
                break
            copied += len(chunk)
            if copied > MAX_FILE_BYTES:
                raise ScreenshotError("Screenshot changed while it was being read")
            _write_all(temporary_fd, chunk)
        if copied != screenshot.size or not _same_file(screenshot, os.fstat(screenshot.fd)):
            raise ScreenshotError("Screenshot changed while it was being read")
        os.fsync(temporary_fd)
        os.close(temporary_fd)
        temporary_fd = None
        if not _validate_cached_file(cache_fd, temporary_name, screenshot):
            raise ScreenshotError("Screenshot changed while it was being read")
        os.replace(temporary_name, cache_name, src_dir_fd=cache_fd, dst_dir_fd=cache_fd)
    except Exception:
        if temporary_fd is not None:
            os.close(temporary_fd)
        try:
            os.unlink(temporary_name, dir_fd=cache_fd)
        except OSError:
            pass
        raise
    return os.path.join(cache_path, cache_name)


def _cleanup_cache(cache_fd: int, keep: set[str]) -> None:
    try:
        names = os.listdir(cache_fd)
    except OSError:
        return
    for name in names:
        if CACHE_NAME_RE.fullmatch(name) and name not in keep:
            try:
                os.unlink(name, dir_fd=cache_fd)
            except OSError:
                pass


def list_screenshots() -> dict[str, object]:
    directory = screenshots_dir()
    directory_fd = _open_directory(directory)
    candidates: list[tuple[int, str]] = []
    try:
        for name in os.listdir(directory_fd):
            if not SCREENSHOT_NAME_RE.fullmatch(name):
                continue
            try:
                screenshot = _open_screenshot_at(directory_fd, directory, name)
            except ScreenshotError:
                continue
            candidates.append((screenshot.mtime_ns, name))
            os.close(screenshot.fd)

        candidates.sort(reverse=True)
        total = len(candidates)
        cache_fd, cache_path = _open_cache_directory()
        matches: list[dict[str, object]] = []
        keep: set[str] = set()
        try:
            for _, name in candidates:
                if len(matches) >= MAX_LIST_COUNT:
                    break
                screenshot = None
                try:
                    screenshot = _open_screenshot_at(directory_fd, directory, name)
                    preview_path = _materialize_preview(cache_fd, cache_path, screenshot)
                    item = {
                        "path": screenshot.path,
                        "previewPath": preview_path,
                        "name": screenshot.name,
                        "size": screenshot.size,
                        "humanSize": human_size(screenshot.size),
                        "width": screenshot.width,
                        "height": screenshot.height,
                        "mtimeIso": datetime.fromtimestamp(
                            screenshot.mtime_ns / 1_000_000_000
                        ).astimezone().isoformat(timespec="seconds"),
                    }
                except ScreenshotError:
                    continue
                finally:
                    if screenshot is not None:
                        os.close(screenshot.fd)
                keep.add(os.path.basename(preview_path))
                matches.append(item)
            _cleanup_cache(cache_fd, keep)
        finally:
            os.close(cache_fd)
    finally:
        os.close(directory_fd)

    return {
        "dir": directory,
        "dirName": os.path.basename(directory),
        "count": len(matches),
        "total": total,
        "screenshots": matches,
    }


def _state_directory() -> str:
    base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
    return os.path.join(os.path.abspath(os.path.expanduser(base)), "omarchy", "screenshot-manager")


def _read_seen() -> int | None:
    """Milliseconds of the newest screenshot the user has already been shown.

    None means there is no usable marker — absent, unreadable, or corrupt.
    Zero is a real answer, and a different one: it is what an empty screenshots
    directory records, and it has to survive the first screenshot landing in
    that directory. Folding the two together re-seeds the marker on the very
    screenshot it should be announcing.
    """
    try:
        fd = os.open(os.path.join(_state_directory(), SEEN_FILE_NAME), _file_flags())
    except OSError:
        return None
    try:
        metadata = os.fstat(fd)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_SEEN_BYTES:
            return None
        raw = os.read(fd, MAX_SEEN_BYTES)
    except OSError:
        return None
    finally:
        os.close(fd)
    try:
        value = int(raw.decode("ascii").strip() or "0")
    except (UnicodeDecodeError, ValueError):
        return None
    return value if value >= 0 else None


def _write_seen(stamp_ms: int) -> int:
    value = max(0, int(stamp_ms))
    directory = _state_directory()
    path = os.path.join(directory, SEEN_FILE_NAME)
    temporary = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        fd = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            _write_all(fd, str(value).encode("ascii"))
        finally:
            os.close(fd)
        os.replace(temporary, path)
    except OSError as error:
        with contextlib.suppress(OSError):
            os.unlink(temporary)
        raise ScreenshotError("Could not record the seen marker") from error
    return value


def _screenshot_stamps() -> tuple[str, list[tuple[int, str]]]:
    """(directory, [(mtime_ms, name)]) newest first.

    Lighter than `list` in that it materializes no preview and hashes nothing,
    but it admits exactly the same files, by calling the same opener. A cheaper
    check that skipped the PNG header would count screenshots the panel then
    refuses to show — the bar would report one waiting and the list would open
    empty — and would contradict the README's promise that over-limit images
    are ignored. The header is 24 bytes at a known offset; correctness is worth
    the read.
    """
    directory = screenshots_dir()
    directory_fd = _open_directory(directory)
    stamps: list[tuple[int, str]] = []
    try:
        for name in os.listdir(directory_fd):
            if not SCREENSHOT_NAME_RE.fullmatch(name):
                continue
            try:
                screenshot = _open_screenshot_at(directory_fd, directory, name)
            except ScreenshotError:
                continue
            stamps.append((screenshot.mtime_ns // 1_000_000, name))
            os.close(screenshot.fd)
    finally:
        os.close(directory_fd)
    stamps.sort(reverse=True)
    return directory, stamps


def status(*, mark_seen: bool = False) -> dict[str, object]:
    directory, stamps = _screenshot_stamps()
    latest_ms = stamps[0][0] if stamps else 0
    latest_name = stamps[0][1] if stamps else ""

    seen_ms = _read_seen()
    # Nothing on disk when the widget is first enabled is "new": it all predates
    # the marker existing. Starting the marker at zero would light the bar up on
    # first run for a directory the user has never once thought of as unread.
    #
    # `is None` rather than `<= 0`: an empty directory legitimately records a
    # marker of zero, and that zero must be kept, or the first screenshot to
    # arrive would be treated as another cold start and silently marked seen.
    if seen_ms is None or mark_seen:
        seen_ms = _write_seen(latest_ms)

    return {
        "dir": directory,
        "dirName": os.path.basename(directory),
        "total": len(stamps),
        "latest": os.path.join(directory, latest_name) if latest_name else "",
        "latestStamp": latest_ms,
        "seenStamp": seen_ms,
        "newCount": sum(1 for stamp_ms, _ in stamps if stamp_ms > seen_ms),
    }


def run_checked(arguments: Sequence[str], *, quiet: bool = False) -> None:
    stdout = subprocess.DEVNULL if quiet else subprocess.PIPE
    stderr = subprocess.DEVNULL if quiet else subprocess.PIPE
    result = subprocess.run(list(arguments), stdout=stdout, stderr=stderr)
    if result.returncode != 0:
        detail = ""
        if not quiet and result.stderr is not None:
            detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise ScreenshotError(detail or "command failed")


def trash(path: str) -> dict[str, object]:
    validated_path = validate_screenshot_path(path)
    if shutil.which("gio") is None:
        raise ScreenshotError("gio is not installed")
    run_checked(["gio", "trash", validated_path])
    return {"trashed": {"path": validated_path}}


def clear_screenshots() -> dict[str, object]:
    if shutil.which("gio") is None:
        raise ScreenshotError("gio is not installed")
    directory = screenshots_dir()
    directory_fd = _open_directory(directory)
    try:
        names = os.listdir(directory_fd)
    finally:
        os.close(directory_fd)
    trashed: list[str] = []
    for name in names:
        if not SCREENSHOT_NAME_RE.fullmatch(name):
            continue
        path = os.path.join(directory, name)
        try:
            validated_path = validate_screenshot_path(path)
        except ScreenshotError:
            continue
        run_checked(["gio", "trash", validated_path])
        trashed.append(validated_path)
    return {"trashed": trashed}


def _stream_to_clipboard(screenshot: OpenScreenshot) -> None:
    process = subprocess.Popen(
        ["wl-copy", "-t", "image/png"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        if process.stdin is None:
            raise ScreenshotError("Could not open clipboard input")
        os.lseek(screenshot.fd, 0, os.SEEK_SET)
        remaining = screenshot.size
        while remaining:
            chunk = os.read(screenshot.fd, min(COPY_CHUNK_BYTES, remaining))
            if not chunk:
                raise ScreenshotError("Screenshot changed while it was being read")
            process.stdin.write(chunk)
            remaining -= len(chunk)
        if os.read(screenshot.fd, 1) or not _same_file(screenshot, os.fstat(screenshot.fd)):
            raise ScreenshotError("Screenshot changed while it was being read")
        process.stdin.close()
        if process.wait() != 0:
            raise ScreenshotError("command failed")
    except (OSError, BrokenPipeError) as error:
        raise ScreenshotError("Could not copy screenshot") from error
    finally:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process.poll() is None:
            process.terminate()
        process.wait()


def copy(path: str) -> dict[str, object]:
    if shutil.which("wl-copy") is None:
        raise ScreenshotError("wl-copy is not installed")
    with open_screenshot(path) as screenshot:
        _stream_to_clipboard(screenshot)
        copied_path = screenshot.path
    return {"copied": {"path": copied_path}}


def parser() -> argparse.ArgumentParser:
    command_parser = argparse.ArgumentParser(
        description="List, poll, trash, and copy Omarchy screenshots"
    )
    subcommands = command_parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("list")
    subcommands.add_parser("status")
    subcommands.add_parser("seen")
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
    elif args.command == "status":
        result = status()
    elif args.command == "seen":
        result = status(mark_seen=True)
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

from __future__ import annotations

import os
import re
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import screenshotctl


def png_header(width: int = 2, height: int = 2) -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", width, height)
        + b"\x08\x06\x00\x00\x00"
    )


class ScreenshotCtlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.pictures = self.root / "Pictures<b>"
        self.runtime = self.root / "runtime"
        self.pictures.mkdir(mode=0o700)
        self.runtime.mkdir(mode=0o700)
        self.environment = mock.patch.dict(
            os.environ,
            {
                "OMARCHY_SCREENSHOT_DIR": str(self.pictures),
                "XDG_RUNTIME_DIR": str(self.runtime),
            },
            clear=False,
        )
        self.environment.start()

    def tearDown(self) -> None:
        self.environment.stop()
        self.temporary.cleanup()

    def write_png(self, name: str, width: int = 2, height: int = 2) -> Path:
        path = self.pictures / name
        path.write_bytes(png_header(width, height))
        return path

    def test_listing_uses_private_bounded_cache_and_keeps_name_as_data(self) -> None:
        name = "screenshot-<img src=x>.png"
        original = self.write_png(name)

        state = screenshotctl.list_screenshots()

        self.assertEqual(state["dirName"], "Pictures<b>")
        self.assertEqual(state["count"], 1)
        item = state["screenshots"][0]
        self.assertEqual(item["path"], str(original))
        self.assertEqual(item["name"], name)
        self.assertEqual((item["width"], item["height"]), (2, 2))
        preview = Path(item["previewPath"])
        self.assertRegex(preview.name, r"^[0-9a-f]{64}\.png$")
        self.assertNotEqual(preview, original)
        self.assertEqual(preview.read_bytes(), original.read_bytes())
        self.assertEqual(preview.parent.stat().st_mode & 0o077, 0)

    def test_listing_rejects_symlink_fifo_oversize_and_excess_dimensions(self) -> None:
        target = self.write_png("target.png")
        os.symlink(target, self.pictures / "screenshot-link.png")
        os.mkfifo(self.pictures / "screenshot-pipe.png", 0o600)
        oversize = self.pictures / "screenshot-oversize.png"
        with oversize.open("wb") as handle:
            handle.write(png_header())
            handle.truncate(screenshotctl.MAX_FILE_BYTES + 1)
        self.write_png("screenshot-huge.png", 10_000, 10_000)

        state = screenshotctl.list_screenshots()

        self.assertEqual(state["count"], 0)
        self.assertEqual(state["screenshots"], [])

    def test_validation_rejects_symlink(self) -> None:
        target = self.write_png("target.png")
        link = self.pictures / "screenshot-link.png"
        os.symlink(target, link)

        with self.assertRaises(screenshotctl.ScreenshotError):
            screenshotctl.validate_screenshot_path(str(link))

    def test_copy_streams_in_bounded_chunks(self) -> None:
        path = self.write_png("screenshot-copy.png")
        with path.open("ab") as handle:
            handle.write(b"x" * (screenshotctl.COPY_CHUNK_BYTES * 2 + 17))

        sink = TrackingSink()
        process = FakeProcess(sink)
        with (
            mock.patch.object(screenshotctl.shutil, "which", return_value="/usr/bin/wl-copy"),
            mock.patch.object(screenshotctl.subprocess, "Popen", return_value=process),
        ):
            result = screenshotctl.copy(str(path))

        self.assertEqual(result["copied"]["path"], str(path))
        self.assertLessEqual(sink.largest_write, screenshotctl.COPY_CHUNK_BYTES)
        self.assertEqual(bytes(sink.data), path.read_bytes())

    def test_all_qml_text_elements_force_plain_text(self) -> None:
        for filename in ("Panel.qml", "PreviewOverlay.qml"):
            source = Path(filename).read_text(encoding="utf-8")
            for match in re.finditer(r"\bText\s*\{", source):
                block = qml_block(source, match.end() - 1)
                self.assertIn("textFormat: Text.PlainText", block, filename)


class TrackingSink:
    def __init__(self) -> None:
        self.data = bytearray()
        self.largest_write = 0
        self.closed = False

    def write(self, data: bytes) -> int:
        self.largest_write = max(self.largest_write, len(data))
        self.data.extend(data)
        return len(data)

    def close(self) -> None:
        self.closed = True


class FakeProcess:
    def __init__(self, sink: TrackingSink) -> None:
        self.stdin = sink
        self.returncode: int | None = None

    def wait(self) -> int:
        self.returncode = 0
        return 0

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15


def qml_block(source: str, opening_brace: int) -> str:
    depth = 0
    for index in range(opening_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening_brace:index + 1]
    raise AssertionError("unterminated QML block")


if __name__ == "__main__":
    unittest.main()

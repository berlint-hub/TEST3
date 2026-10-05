"""Filesystem watcher for the dump folder (watchdog) with a settle/debounce stage."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

IMAGE_EXTENSIONS = (".png", ".bmp", ".tga", ".jpg", ".jpeg", ".dds")


def is_image_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


class _Handler(FileSystemEventHandler):
    def __init__(self, cb: Callable[[str], None]) -> None:
        self._cb = cb

    def _emit(self, path: str) -> None:
        if is_image_file(path):
            self._cb(path)

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(str(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(str(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self._emit(str(event.dest_path))


class SettleQueue:
    """Collects noisy FS events and releases a path once its size stayed constant for `settle_ms`.

    Emulators write PNGs in several chunks; processing a half-written file would fail or,
    worse, produce a truncated upscale.
    """

    def __init__(self, settle_ms: int, on_ready: Callable[[str], None], poll_ms: int = 100) -> None:
        self._settle = max(0.05, settle_ms / 1000.0)
        self._poll = max(0.02, poll_ms / 1000.0)
        self._on_ready = on_ready
        self._pending: dict[str, tuple[int, float]] = {}  # path -> (size, last_change_ts)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def touch(self, path: str) -> None:
        try:
            size = Path(path).stat().st_size
        except OSError:
            return
        now = time.monotonic()
        with self._lock:
            prev = self._pending.get(path)
            if prev is None or prev[0] != size:
                self._pending[path] = (size, now)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="texup-settle", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        with self._lock:
            self._pending.clear()

    def _loop(self) -> None:
        while not self._stop.is_set():
            time.sleep(self._poll)
            now = time.monotonic()
            ready: list[str] = []
            with self._lock:
                for path, (size, ts) in list(self._pending.items()):
                    try:
                        cur = Path(path).stat().st_size
                    except OSError:
                        del self._pending[path]
                        continue
                    if cur != size:
                        self._pending[path] = (cur, now)
                        continue
                    if cur > 0 and now - ts >= self._settle:
                        ready.append(path)
                        del self._pending[path]
            for path in ready:
                self._on_ready(path)


def start_observer(folder: str, recursive: bool, cb: Callable[[str], None]) -> Observer:
    observer = Observer()
    observer.schedule(_Handler(cb), folder, recursive=recursive)
    observer.daemon = True
    observer.start()
    return observer

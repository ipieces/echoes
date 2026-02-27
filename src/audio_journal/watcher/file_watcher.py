from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer


def wait_stable(
    path: Path,
    *,
    stable_seconds: float,
    poll_interval: float = 0.2,
    timeout_s: float = 300.0,
) -> None:
    """等待文件写入稳定。

    通过轮询文件 size/mtime，连续 stable_seconds 不变则认为写入完成。
    """

    start = time.monotonic()
    last_size: int | None = None
    last_mtime: float | None = None
    stable_for = 0.0

    while True:
        if time.monotonic() - start > timeout_s:
            raise TimeoutError(f"等待文件稳定超时: {path}")

        try:
            stat = path.stat()
        except FileNotFoundError:
            time.sleep(poll_interval)
            continue

        size = stat.st_size
        mtime = stat.st_mtime
        if last_size == size and last_mtime == mtime:
            stable_for += poll_interval
        else:
            stable_for = 0.0

        if stable_for >= stable_seconds:
            return

        last_size = size
        last_mtime = mtime
        time.sleep(poll_interval)


class AudioFileHandler(FileSystemEventHandler):
    def __init__(
        self,
        *,
        patterns: Iterable[str],
        stable_seconds: float,
        on_audio_ready: Callable[[Path], None],
    ) -> None:
        self.patterns = list(patterns)
        self.stable_seconds = stable_seconds
        self.on_audio_ready = on_audio_ready

    def on_created(self, event) -> None:  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return

        p = Path(str(getattr(event, "src_path", "")))
        if p.suffix.lower() != ".wav":
            return

        wait_stable(p, stable_seconds=self.stable_seconds)
        self.on_audio_ready(p)


class FileWatcher:
    """前台文件监听服务（Phase 1 MVP）。"""

    def __init__(self, *, watch_dir: str | Path, patterns: Iterable[str], stable_seconds: float) -> None:
        self.watch_dir = Path(watch_dir)
        self.patterns = list(patterns)
        self.stable_seconds = stable_seconds

    def start(self, on_audio_ready: Callable[[Path], None]) -> None:
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        observer = Observer()
        handler = AudioFileHandler(
            patterns=self.patterns,
            stable_seconds=self.stable_seconds,
            on_audio_ready=on_audio_ready,
        )
        observer.schedule(handler, str(self.watch_dir), recursive=False)
        observer.start()

        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

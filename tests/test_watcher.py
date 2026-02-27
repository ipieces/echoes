from __future__ import annotations

import threading
import time
from pathlib import Path

from audio_journal.watcher.file_watcher import AudioFileHandler, wait_stable


def test_wait_stable_returns_when_file_stops_growing(tmp_path: Path) -> None:
    p = tmp_path / "a.wav"

    def _writer() -> None:
        p.write_bytes(b"1" * 10)
        time.sleep(0.1)
        with p.open("ab") as f:
            f.write(b"2" * 10)

    t = threading.Thread(target=_writer)
    t.start()

    wait_stable(p, stable_seconds=0.2, poll_interval=0.05, timeout_s=5.0)
    t.join(timeout=2)
    assert p.stat().st_size == 20


def test_handler_ignores_non_wav(tmp_path: Path) -> None:
    called: list[Path] = []

    handler = AudioFileHandler(
        patterns=["*.wav"],
        stable_seconds=0.0,
        on_audio_ready=lambda p: called.append(p),
    )

    class _Evt:
        is_directory = False

        def __init__(self, src_path: str) -> None:
            self.src_path = src_path

    handler.on_created(_Evt(str(tmp_path / "a.txt")))
    assert called == []

from __future__ import annotations

import math
import wave
from pathlib import Path

from audio_journal.chunker.vad_chunker import VADChunker
from audio_journal.config import ChunkerConfig


def _tone(duration_s: float, sr: int, amp: int = 10000, freq: float = 440.0) -> list[int]:
    n = int(sr * duration_s)
    return [int(amp * math.sin(2 * math.pi * freq * i / sr)) for i in range(n)]


def _silence(duration_s: float, sr: int) -> list[int]:
    return [0] * int(sr * duration_s)


def _write_wav(path: Path, samples: list[int], sr: int) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"".join(int(s).to_bytes(2, byteorder="little", signed=True) for s in samples))


def test_chunker_splits_on_long_silence(tmp_path: Path) -> None:
    sr = 8000
    samples = _tone(0.2, sr) + _silence(0.6, sr) + _tone(0.2, sr)
    wav_path = tmp_path / "a.wav"
    _write_wav(wav_path, samples, sr)

    cfg = ChunkerConfig(min_silence_gap=0.5, max_chunk_duration=10.0, min_chunk_duration=0.0)
    out_dir = tmp_path / "chunks"

    chunks = VADChunker(cfg).split(wav_path, out_dir)
    assert len(chunks) == 2
    assert chunks[0].path.exists()
    assert chunks[1].path.exists()


def test_chunker_enforces_max_duration(tmp_path: Path) -> None:
    sr = 8000
    samples = _tone(0.6, sr)
    wav_path = tmp_path / "b.wav"
    _write_wav(wav_path, samples, sr)

    cfg = ChunkerConfig(min_silence_gap=10.0, max_chunk_duration=0.3, min_chunk_duration=0.0)
    chunks = VADChunker(cfg).split(wav_path, tmp_path / "chunks")

    assert len(chunks) == 2
    assert chunks[0].duration <= 0.31
    assert chunks[1].duration <= 0.31


def test_chunker_merges_too_short_tail_chunk(tmp_path: Path) -> None:
    sr = 8000
    samples = _tone(0.65, sr)
    wav_path = tmp_path / "c.wav"
    _write_wav(wav_path, samples, sr)

    cfg = ChunkerConfig(min_silence_gap=10.0, max_chunk_duration=0.3, min_chunk_duration=0.1)
    chunks = VADChunker(cfg).split(wav_path, tmp_path / "chunks")

    assert len(chunks) == 2
    assert chunks[0].duration <= 0.31
    assert chunks[1].duration >= 0.33

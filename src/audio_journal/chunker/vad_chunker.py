from __future__ import annotations

import math
from array import array
from dataclasses import dataclass
from pathlib import Path

import wave

from audio_journal.config import ChunkerConfig


@dataclass(frozen=True)
class Chunk:
    path: Path
    start_time: float
    end_time: float
    duration: float


class VADChunker:
    """基于静音检测的 WAV 预切分器（Phase 1 MVP）。

    说明：MVP 阶段不引入模型级 VAD，仅支持 PCM WAV，通过能量检测近似静音。
    """

    def __init__(self, config: ChunkerConfig) -> None:
        self.config = config
        self._frame_ms: int = 30

    def split(self, audio_path: str | Path, output_dir: str | Path) -> list[Chunk]:
        src = Path(audio_path)
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        with wave.open(str(src), "rb") as wf:
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            if sampwidth != 2:
                raise ValueError("仅支持 16-bit PCM WAV")

            frames = wf.readframes(nframes)

        samples = array("h")
        samples.frombytes(frames)
        if nchannels > 1:
            # MVP：仅取第一个声道，避免引入额外依赖。
            samples = array("h", samples[0::nchannels])
            nchannels = 1

        total_frames = len(samples)
        frame_size = max(1, int(framerate * self._frame_ms / 1000))
        frame_dur = frame_size / framerate

        silent_frames: list[bool] = []
        for i in range(0, total_frames, frame_size):
            frame = samples[i : i + frame_size]
            if not frame:
                break
            rms = math.sqrt(sum(x * x for x in frame) / len(frame))
            silent_frames.append(rms <= self.config.silence_rms_threshold)

        silence_cutpoints: list[int] = []
        run_start = None
        for idx, is_silent in enumerate(silent_frames + [False]):
            if is_silent and run_start is None:
                run_start = idx
            if (not is_silent) and run_start is not None:
                run_end = idx  # exclusive
                run_len = run_end - run_start
                if run_len * frame_dur >= self.config.min_silence_gap:
                    mid_frame = (run_start + run_end) // 2
                    cut_sample = min(total_frames, mid_frame * frame_size)
                    if 0 < cut_sample < total_frames:
                        silence_cutpoints.append(cut_sample)
                run_start = None

        silence_cutpoints = sorted(set(silence_cutpoints))

        # 基础切点：静音切点 + 首尾。
        base_cuts = [0, *silence_cutpoints, total_frames]
        base_cuts = sorted(set(base_cuts))

        max_samples = max(1, int(self.config.max_chunk_duration * framerate))
        cuts: list[int] = [base_cuts[0]]
        for target in base_cuts[1:]:
            # 在基础切点之间，如果间隔超过 max_duration，则插入强制切点。
            while target - cuts[-1] > max_samples:
                cuts.append(cuts[-1] + max_samples)
            if target != cuts[-1]:
                cuts.append(target)

        # 合并过短的尾部 chunk（常见于 max_duration 强制切分的余数）。
        min_samples = int(self.config.min_chunk_duration * framerate)
        while len(cuts) > 2 and (cuts[-1] - cuts[-2]) < min_samples:
            cuts.pop(-2)

        chunks: list[Chunk] = []
        params = (nchannels, 2, framerate, 0, "NONE", "not compressed")
        for i, (start, end) in enumerate(zip(cuts[:-1], cuts[1:], strict=True), start=1):
            chunk_path = out_dir / f"chunk_{i:03d}.wav"
            with wave.open(str(chunk_path), "wb") as wf:
                wf.setparams(params)
                data = samples[start:end]
                wf.writeframes(data.tobytes())

            start_time = start / framerate
            end_time = end / framerate
            chunks.append(
                Chunk(
                    path=chunk_path,
                    start_time=start_time,
                    end_time=end_time,
                    duration=end_time - start_time,
                )
            )

        return chunks

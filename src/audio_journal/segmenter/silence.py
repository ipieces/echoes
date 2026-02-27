from __future__ import annotations

from pathlib import Path

from audio_journal.config import SegmenterConfig
from audio_journal.models.schemas import Segment, Utterance


class SilenceSegmenter:
    """基于静音间隔与最大时长的分段器。"""

    def __init__(self, config: SegmenterConfig) -> None:
        self.config = config

    def segment(self, utterances: list[Utterance], source_file: str) -> list[Segment]:
        if not utterances:
            return []

        ordered = sorted(utterances, key=lambda u: (u.start_time, u.end_time))
        segments: list[Segment] = []

        cur_utts: list[Utterance] = []
        cur_start = ordered[0].start_time
        cur_end = ordered[0].end_time

        def _flush() -> None:
            nonlocal cur_utts, cur_start, cur_end
            if not cur_utts:
                return
            duration = cur_end - cur_start
            if duration < self.config.min_segment_duration:
                cur_utts = []
                return
            seg_id = self._make_segment_id(source_file, cur_start, cur_end)
            segments.append(
                Segment(
                    id=seg_id,
                    utterances=cur_utts,
                    start_time=cur_start,
                    end_time=cur_end,
                    duration=duration,
                    source_file=source_file,
                )
            )
            cur_utts = []

        prev = None
        for utt in ordered:
            if prev is None:
                cur_utts = [utt]
                cur_start = utt.start_time
                cur_end = utt.end_time
                prev = utt
                continue

            gap = max(0.0, utt.start_time - prev.end_time)
            # 规则 1：长静音分段。
            if gap > self.config.min_silence_gap:
                _flush()
                cur_utts = [utt]
                cur_start = utt.start_time
                cur_end = utt.end_time
                prev = utt
                continue

            # 规则 2：超过最大时长则强制切分（在 utterance 边界）。
            if (utt.end_time - cur_start) > self.config.max_segment_duration and cur_utts:
                _flush()
                cur_utts = [utt]
                cur_start = utt.start_time
                cur_end = utt.end_time
                prev = utt
                continue

            cur_utts.append(utt)
            cur_end = max(cur_end, utt.end_time)
            prev = utt

        _flush()
        return segments

    @staticmethod
    def _make_segment_id(source_file: str, start: float, end: float) -> str:
        stem = Path(source_file).stem
        return f"{stem}-{start:.2f}-{end:.2f}"

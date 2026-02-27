from __future__ import annotations

from audio_journal.config import SegmenterConfig
from audio_journal.models.schemas import Speaker, Utterance
from audio_journal.segmenter.silence import SilenceSegmenter


def _utt(start: float, end: float, text: str = "x", spk: str = "SPEAKER_00") -> Utterance:
    return Utterance(
        speaker=Speaker(id=spk),
        text=text,
        start_time=start,
        end_time=end,
    )


def test_segmenter_splits_on_gap() -> None:
    cfg = SegmenterConfig(min_silence_gap=3.0, max_segment_duration=999.0, min_segment_duration=0.0)
    segs = SilenceSegmenter(cfg).segment([
        _utt(0.0, 1.0, "a"),
        _utt(10.0, 11.0, "b"),
    ], source_file="a.wav")

    assert len(segs) == 2
    assert segs[0].start_time == 0.0
    assert segs[1].start_time == 10.0


def test_segmenter_enforces_max_duration() -> None:
    cfg = SegmenterConfig(min_silence_gap=999.0, max_segment_duration=5.0, min_segment_duration=0.0)
    segs = SilenceSegmenter(cfg).segment([
        _utt(0.0, 2.0),
        _utt(2.1, 4.0),
        _utt(4.1, 6.0),
    ], source_file="b.wav")

    assert len(segs) == 2
    assert segs[0].duration <= 5.0


def test_segmenter_drops_too_short() -> None:
    cfg = SegmenterConfig(min_silence_gap=999.0, max_segment_duration=999.0, min_segment_duration=3.0)
    segs = SilenceSegmenter(cfg).segment([
        _utt(0.0, 1.0),
        _utt(1.1, 2.0),
    ], source_file="c.wav")

    assert segs == []

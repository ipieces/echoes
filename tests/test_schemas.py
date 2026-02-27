from __future__ import annotations

from audio_journal.models.schemas import (
    AnalysisResult,
    ClassifiedSegment,
    SceneType,
    Segment,
    Speaker,
    Utterance,
)


def test_utterance_segment_roundtrip() -> None:
    utt1 = Utterance(
        speaker=Speaker(id="SPEAKER_00", label="我"),
        text="你好",
        start_time=1.0,
        end_time=2.0,
    )
    utt2 = Utterance(
        speaker=Speaker(id="SPEAKER_01"),
        text="嗯",
        start_time=2.5,
        end_time=3.0,
    )

    seg = Segment(
        id="seg-1",
        utterances=[utt1, utt2],
        start_time=1.0,
        end_time=3.0,
        duration=2.0,
        source_file="a.wav",
    )

    dumped = seg.model_dump_json()
    loaded = Segment.model_validate_json(dumped)
    assert loaded == seg

    cseg = ClassifiedSegment(
        **seg.model_dump(),
        scene=SceneType.MEETING,
        confidence=0.9,
        value_tags=[],
    )
    dumped2 = cseg.model_dump_json()
    loaded2 = ClassifiedSegment.model_validate_json(dumped2)
    assert loaded2 == cseg


def test_analysis_result_accepts_metadata() -> None:
    r = AnalysisResult(
        segment_id="seg-1",
        scene=SceneType.MEETING,
        raw_text="[00:00] ...",
        metadata={"a": {"b": [1, 2, 3]}, "x": ["y"]},
    )
    assert r.metadata["a"]["b"] == [1, 2, 3]

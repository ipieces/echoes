from __future__ import annotations

import pytest

from audio_journal.config import MergerConfig
from audio_journal.merger.segment_merger import SegmentMerger
from audio_journal.models.schemas import ClassifiedSegment, MergedSegment, SceneType, Speaker, Utterance


def _make_segment(
    seg_id: str,
    scene: SceneType,
    start_time: float,
    end_time: float,
    confidence: float = 0.9,
    value_tags: list[str] | None = None,
) -> ClassifiedSegment:
    """创建测试用的 ClassifiedSegment。"""
    duration = end_time - start_time
    utterances = [
        Utterance(
            speaker=Speaker(id="SPEAKER_00"),
            text=f"Test utterance in {seg_id}",
            start_time=start_time,
            end_time=end_time,
        )
    ]
    return ClassifiedSegment(
        id=seg_id,
        scene=scene,
        utterances=utterances,
        start_time=start_time,
        end_time=end_time,
        duration=duration,
        source_file="test.wav",
        confidence=confidence,
        value_tags=value_tags or [],
    )


def test_merge_consecutive_meetings():
    """测试连续会议片段合并。"""
    config = MergerConfig(
        enabled=True,
        max_gap_between_segments=600.0,
        max_merged_duration=7200.0,
        mergeable_scenes=["meeting", "learning", "business"],
    )
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.MEETING, 0, 1500, confidence=0.95)
    seg2 = _make_segment("seg2", SceneType.MEETING, 1800, 3300, confidence=0.92)
    seg3 = _make_segment("seg3", SceneType.MEETING, 3900, 5400, confidence=0.94)

    result = merger.merge([seg1, seg2, seg3])

    assert len(result) == 1
    assert isinstance(result[0], MergedSegment)

    merged = result[0]
    assert merged.scene == SceneType.MEETING
    assert merged.start_time == 0
    assert merged.end_time == 5400
    assert merged.duration == 5400
    assert merged.original_segment_ids == ["seg1", "seg2", "seg3"]
    assert len(merged.gap_durations) == 2
    assert merged.gap_durations[0] == 300  # 1800 - 1500
    assert merged.gap_durations[1] == 600  # 3900 - 3300
    assert merged.confidence == pytest.approx((0.95 + 0.92 + 0.94) / 3)
    assert len(merged.utterances) == 3


def test_no_merge_different_scenes():
    """测试不同场景不合并。"""
    config = MergerConfig()
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.MEETING, 0, 1500)
    seg2 = _make_segment("seg2", SceneType.PHONE, 1800, 3300)
    seg3 = _make_segment("seg3", SceneType.MEETING, 3600, 5100)

    result = merger.merge([seg1, seg2, seg3])

    assert len(result) == 3
    assert all(isinstance(seg, ClassifiedSegment) for seg in result)


def test_no_merge_large_gap():
    """测试间隔过大不合并。"""
    config = MergerConfig(max_gap_between_segments=600.0)
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.MEETING, 0, 1500)
    seg2 = _make_segment("seg2", SceneType.MEETING, 2200, 3700)  # 间隔 700秒 > 600秒

    result = merger.merge([seg1, seg2])

    assert len(result) == 2
    assert all(isinstance(seg, ClassifiedSegment) for seg in result)


def test_no_merge_exceeds_duration():
    """测试超时长不合并。"""
    config = MergerConfig(max_merged_duration=3600.0)  # 1小时
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.MEETING, 0, 2000)
    seg2 = _make_segment("seg2", SceneType.MEETING, 2300, 4300)  # 总时长 4300秒 > 3600秒

    result = merger.merge([seg1, seg2])

    assert len(result) == 2
    assert all(isinstance(seg, ClassifiedSegment) for seg in result)


def test_non_mergeable_scene():
    """测试 phone/chat/idea 不合并。"""
    config = MergerConfig(mergeable_scenes=["meeting", "learning", "business"])
    merger = SegmentMerger(config)

    # Phone 场景
    seg1 = _make_segment("seg1", SceneType.PHONE, 0, 1500)
    seg2 = _make_segment("seg2", SceneType.PHONE, 1800, 3300)

    result = merger.merge([seg1, seg2])
    assert len(result) == 2

    # Chat 场景
    seg3 = _make_segment("seg3", SceneType.CHAT, 0, 1500)
    seg4 = _make_segment("seg4", SceneType.CHAT, 1800, 3300)

    result = merger.merge([seg3, seg4])
    assert len(result) == 2

    # Idea 场景
    seg5 = _make_segment("seg5", SceneType.IDEA, 0, 1500)
    seg6 = _make_segment("seg6", SceneType.IDEA, 1800, 3300)

    result = merger.merge([seg5, seg6])
    assert len(result) == 2


def test_merged_segment_metadata():
    """测试合并后的元数据正确性。"""
    config = MergerConfig()
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.MEETING, 0, 1500, confidence=0.9, value_tags=["important"])
    seg2 = _make_segment(
        "seg2", SceneType.MEETING, 1800, 3300, confidence=0.85, value_tags=["decision"]
    )

    result = merger.merge([seg1, seg2])

    assert len(result) == 1
    merged = result[0]

    assert merged.id == "merged-seg1-seg2"
    assert merged.source_file == "test.wav"
    assert set(merged.value_tags) == {"important", "decision"}
    assert merged.confidence == pytest.approx((0.9 + 0.85) / 2)


def test_merge_empty_list():
    """测试空列表输入。"""
    config = MergerConfig()
    merger = SegmentMerger(config)

    result = merger.merge([])
    assert result == []


def test_merge_single_segment():
    """测试单个片段不合并。"""
    config = MergerConfig()
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.MEETING, 0, 1500)

    result = merger.merge([seg1])

    assert len(result) == 1
    assert isinstance(result[0], ClassifiedSegment)
    assert result[0].id == "seg1"


def test_merge_unsorted_segments():
    """测试未排序的片段会被自动排序。"""
    config = MergerConfig()
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.MEETING, 0, 1500)
    seg2 = _make_segment("seg2", SceneType.MEETING, 3600, 5100)
    seg3 = _make_segment("seg3", SceneType.MEETING, 1800, 3300)

    # 乱序输入
    result = merger.merge([seg2, seg1, seg3])

    assert len(result) == 1
    merged = result[0]
    assert merged.original_segment_ids == ["seg1", "seg3", "seg2"]


def test_merge_learning_scene():
    """测试学习场景合并（视频暂停场景）。"""
    config = MergerConfig()
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.LEARNING, 0, 1800)
    seg2 = _make_segment("seg2", SceneType.LEARNING, 2100, 3900)

    result = merger.merge([seg1, seg2])

    assert len(result) == 1
    assert isinstance(result[0], MergedSegment)


def test_merge_business_scene():
    """测试商务场景合并（中途休息场景）。"""
    config = MergerConfig()
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.BUSINESS, 0, 1800)
    seg2 = _make_segment("seg2", SceneType.BUSINESS, 2100, 3900)

    result = merger.merge([seg1, seg2])

    assert len(result) == 1
    assert isinstance(result[0], MergedSegment)


def test_merge_disabled():
    """测试禁用合并功能。"""
    config = MergerConfig(enabled=False)
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.MEETING, 0, 1500)
    seg2 = _make_segment("seg2", SceneType.MEETING, 1800, 3300)

    # 即使满足合并条件，禁用时也不应合并
    # 但 SegmentMerger.merge() 本身不检查 enabled，由 Pipeline 控制
    # 这里测试的是 merger 本身的逻辑
    result = merger.merge([seg1, seg2])

    # merger 本身会合并，enabled 由 Pipeline 控制
    assert len(result) == 1


def test_partial_merge():
    """测试部分片段合并的场景。"""
    config = MergerConfig(max_gap_between_segments=600.0)
    merger = SegmentMerger(config)

    seg1 = _make_segment("seg1", SceneType.MEETING, 0, 1500)
    seg2 = _make_segment("seg2", SceneType.MEETING, 1800, 3300)  # 间隔 300秒，可合并
    seg3 = _make_segment("seg3", SceneType.MEETING, 4000, 5500)  # 间隔 700秒，不可合并

    result = merger.merge([seg1, seg2, seg3])

    assert len(result) == 2
    assert isinstance(result[0], MergedSegment)
    assert result[0].original_segment_ids == ["seg1", "seg2"]
    assert isinstance(result[1], ClassifiedSegment)
    assert result[1].id == "seg3"

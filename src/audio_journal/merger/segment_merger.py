from __future__ import annotations

from audio_journal.config import MergerConfig
from audio_journal.models.schemas import ClassifiedSegment, MergedSegment, Utterance


class SegmentMerger:
    """场景感知的 Segment 合并器。"""

    def __init__(self, config: MergerConfig) -> None:
        self.config = config

    def merge(
        self, segments: list[ClassifiedSegment]
    ) -> list[ClassifiedSegment | MergedSegment]:
        """
        对输入的 ClassifiedSegment 列表进行合并。

        返回:
            合并后的列表，包含 MergedSegment 和未合并的 ClassifiedSegment
        """
        if not segments:
            return []

        # 按时间排序
        sorted_segments = sorted(segments, key=lambda s: s.start_time)

        result: list[ClassifiedSegment | MergedSegment] = []
        current_group: list[ClassifiedSegment] = [sorted_segments[0]]

        for seg in sorted_segments[1:]:
            if self._should_merge(current_group[-1], seg):
                current_group.append(seg)
            else:
                # 当前组结束，决定是否合并
                result.extend(self._finalize_group(current_group))
                current_group = [seg]

        # 处理最后一组
        result.extend(self._finalize_group(current_group))

        return result

    def _should_merge(self, seg1: ClassifiedSegment, seg2: ClassifiedSegment) -> bool:
        """判断两个相邻 Segment 是否应该合并。"""

        # 规则1: 场景一致性
        if seg1.scene != seg2.scene:
            return False

        # 规则4: 场景特定策略
        if seg1.scene.value not in self.config.mergeable_scenes:
            return False

        # 规则2: 时间连续性
        gap = seg2.start_time - seg1.end_time
        if gap > self.config.max_gap_between_segments:
            return False

        return True

    def _finalize_group(
        self, group: list[ClassifiedSegment]
    ) -> list[ClassifiedSegment | MergedSegment]:
        """
        决定一组 Segment 是否合并。

        - 如果只有1个 Segment，直接返回
        - 如果有多个 Segment，检查合并后时长，决定是否合并
        """
        if len(group) == 1:
            return group

        # 规则3: 合并后时长限制
        total_duration = sum(seg.duration for seg in group)
        if total_duration > self.config.max_merged_duration:
            # 超过时长限制，不合并
            return group

        # 执行合并
        merged = self._create_merged_segment(group)
        return [merged]

    def _create_merged_segment(self, segments: list[ClassifiedSegment]) -> MergedSegment:
        """创建合并后的 MergedSegment。"""

        # 合并所有 utterances
        all_utterances: list[Utterance] = []
        for seg in segments:
            all_utterances.extend(seg.utterances)

        # 按时间排序
        all_utterances.sort(key=lambda u: u.start_time)

        # 计算间隔
        gap_durations: list[float] = []
        for i in range(len(segments) - 1):
            gap = segments[i + 1].start_time - segments[i].end_time
            gap_durations.append(gap)

        # 合并 value_tags
        all_value_tags = []
        for seg in segments:
            all_value_tags.extend(seg.value_tags)
        unique_value_tags = list(set(all_value_tags))

        # 计算平均置信度
        avg_confidence = sum(seg.confidence for seg in segments) / len(segments)

        # 生成合并 ID
        merged_id = "merged-" + "-".join(seg.id for seg in segments)

        return MergedSegment(
            id=merged_id,
            scene=segments[0].scene,
            utterances=all_utterances,
            start_time=segments[0].start_time,
            end_time=segments[-1].end_time,
            duration=segments[-1].end_time - segments[0].start_time,
            source_file=segments[0].source_file,
            original_segment_ids=[seg.id for seg in segments],
            gap_durations=gap_durations,
            confidence=avg_confidence,
            value_tags=unique_value_tags,
        )

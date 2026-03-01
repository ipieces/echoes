# 场景感知的 Segment 合并策略设计

## 背景

### 问题描述

当前 Segmenter 基于静音间隔切分对话片段,存在以下问题:

**场景**: 2小时会议,中间有3次茶歇(每次5-10分钟静音)

```
会议录音 (120分钟)
├─ 00:00-00:25 讨论议题A → Segment 1 (scene: meeting)
│   [静音 5分钟 - 茶歇]
├─ 00:30-00:55 讨论议题B → Segment 2 (scene: meeting)
│   [静音 10分钟 - 茶歇]
├─ 01:05-01:35 讨论议题C → Segment 3 (scene: meeting)
│   [静音 3分钟 - 茶歇]
└─ 01:38-02:00 做出决策 → Segment 4 (scene: meeting)
```

**当前行为**:
- 4个 Segment 被独立分类和分析
- 每个 Segment 生成独立的分析结果
- 丢失会议的整体上下文和议程连贯性

**期望行为**:
- 识别这4个 Segment 属于同一场会议
- 合并后进行整体分析
- 生成一份完整的会议纪要

---

## 设计方案

### 核心思路

在 **分类后、分析前** 插入合并逻辑:

```
Segmenter → Classifier → [Merger] → Analyzer → Archiver
```

### 合并规则

#### 规则1: 场景一致性
连续的 Segment 必须属于同一场景类型才考虑合并。

```python
# 可合并
[meeting, meeting, meeting] → 合并

# 不可合并
[meeting, phone, meeting] → 保持独立
```

#### 规则2: 时间连续性
相邻 Segment 的时间间隔不超过阈值。

```python
# 配置
merger:
  max_gap_between_segments: 600  # 秒，最大允许间隔10分钟

# 判断逻辑
gap = segment2.start_time - segment1.end_time
if gap <= max_gap_between_segments:
    可以合并
```

#### 规则3: 合并后时长限制
合并后的总时长不超过上限,避免超长文本影响 LLM 分析质量。

```python
# 配置
merger:
  max_merged_duration: 7200  # 秒，合并后最长2小时

# 判断逻辑
total_duration = sum(seg.duration for seg in segments_to_merge)
if total_duration <= max_merged_duration:
    可以合并
```

#### 规则4: 场景特定策略
不同场景有不同的合并倾向。

```python
# 配置
merger:
  mergeable_scenes:
    - meeting      # 会议:强烈建议合并(茶歇场景)
    - learning     # 学习:建议合并(视频暂停场景)
    - business     # 商务:建议合并(中途休息场景)

  non_mergeable_scenes:
    - phone        # 电话:通常不合并(一通电话结束就是结束)
    - chat         # 闲聊:通常不合并(话题跳跃)
    - idea         # 灵感:通常不合并(独立思考片段)
```

---

## 实现设计

### 数据结构

#### MergedSegment

```python
from dataclasses import dataclass
from audio_journal.models.schemas import ClassifiedSegment, Utterance

@dataclass
class MergedSegment:
    """合并后的 Segment,保留原始 Segment 信息以便追溯。"""

    id: str  # 合并后的唯一标识,如 "merged-seg1-seg2-seg3"
    scene: SceneType
    utterances: list[Utterance]  # 所有原始 Segment 的 utterances 合并
    start_time: float  # 第一个 Segment 的开始时间
    end_time: float  # 最后一个 Segment 的结束时间
    duration: float  # 总时长
    source_file: str

    # 元数据
    original_segment_ids: list[str]  # 原始 Segment ID 列表
    gap_durations: list[float]  # 各段之间的静音间隔时长
    confidence: float  # 取原始 Segment 置信度的平均值
    value_tags: list[str]  # 合并所有原始 Segment 的 value_tags
```

### 核心模块

#### SegmentMerger

```python
from pathlib import Path
from audio_journal.models.schemas import ClassifiedSegment, SceneType

class SegmentMerger:
    """场景感知的 Segment 合并器。"""

    def __init__(self, config: MergerConfig):
        self.config = config

    def merge(self, segments: list[ClassifiedSegment]) -> list[ClassifiedSegment | MergedSegment]:
        """
        对输入的 ClassifiedSegment 列表进行合并。

        返回:
            合并后的列表,包含 MergedSegment 和未合并的 ClassifiedSegment
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
                # 当前组结束,决定是否合并
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
        if seg1.scene not in self.config.mergeable_scenes:
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

        - 如果只有1个 Segment,直接返回
        - 如果有多个 Segment,检查合并后时长,决定是否合并
        """
        if len(group) == 1:
            return group

        # 规则3: 合并后时长限制
        total_duration = sum(seg.duration for seg in group)
        if total_duration > self.config.max_merged_duration:
            # 超过时长限制,不合并
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
```

### 配置定义

```python
# src/audio_journal/config.py

class MergerConfig(BaseModel):
    """Segment 合并器配置。"""

    enabled: bool = True  # 是否启用合并功能

    max_gap_between_segments: float = 600.0  # 秒,最大允许间隔(10分钟)
    max_merged_duration: float = 7200.0  # 秒,合并后最长时长(2小时)

    mergeable_scenes: list[str] = Field(
        default_factory=lambda: ["meeting", "learning", "business"]
    )
```

```yaml
# config.yaml

# Segment 合并配置
merger:
  enabled: true
  max_gap_between_segments: 600  # 秒,相邻 Segment 最大间隔(10分钟)
  max_merged_duration: 7200  # 秒,合并后最长时长(2小时)
  mergeable_scenes:
    - meeting
    - learning
    - business
```

---

## Pipeline 集成

### 修改 Pipeline 流程

```python
# src/audio_journal/pipeline.py

class Pipeline:
    def __init__(
        self,
        config: AppConfig,
        *,
        chunker: Optional[VADChunker] = None,
        asr: Optional[ASREngine] = None,
        segmenter: Optional[SilenceSegmenter] = None,
        classifier: Optional[SceneClassifier] = None,
        merger: Optional[SegmentMerger] = None,  # 新增
        meeting_analyzer: Optional[MeetingAnalyzer] = None,
        archiver: Optional[LocalArchiver] = None,
    ) -> None:
        self.config = config
        self.chunker = chunker or VADChunker(config.chunker)
        self.asr = asr or _default_asr(config)
        self.segmenter = segmenter or SilenceSegmenter(config.segmenter)
        self.classifier = classifier or _default_classifier(config)
        self.merger = merger or SegmentMerger(config.merger)  # 新增
        self.meeting_analyzer = meeting_analyzer or _default_meeting_analyzer(config)
        self.passthrough_analyzer = PassthroughAnalyzer()
        self.archiver = archiver or LocalArchiver(base_dir=config.archive.local.base_dir)

    async def process(self, audio_path: str | Path) -> list[AnalysisResult]:
        src = Path(audio_path)
        run_dir = (self.config.paths.processing / src.stem).resolve()
        chunks_dir = run_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        chunks = self.chunker.split(src, chunks_dir)

        all_results: list[AnalysisResult] = []
        for chunk in chunks:
            utterances = self.asr.transcribe(str(chunk.path))
            segments = self.segmenter.segment(utterances, source_file=str(src.name))

            # 分类
            classified: list[ClassifiedSegment] = []
            for seg in segments:
                classified.append(await self.classifier.classify(seg))

            # 合并 (新增)
            if self.config.merger.enabled:
                merged_segments = self.merger.merge(classified)
            else:
                merged_segments = classified

            # 分析
            for seg in merged_segments:
                if seg.scene == SceneType.MEETING:
                    res = await self.meeting_analyzer.analyze(seg)
                else:
                    res = await self.passthrough_analyzer.analyze(seg)
                all_results.append(res)

        # 归档
        self.archiver.archive_all(all_results, source_file=str(src.name))
        return all_results
```

---

## 效果示例

### 输入

```
chunk_001.wav 转写后的 Segments:
├─ Segment 1: 00:00-00:25 (25分钟, scene: meeting, confidence: 0.95)
├─ Segment 2: 00:30-00:55 (25分钟, scene: meeting, confidence: 0.92)
├─ Segment 3: 01:05-01:35 (30分钟, scene: meeting, confidence: 0.94)
└─ Segment 4: 01:38-02:00 (22分钟, scene: meeting, confidence: 0.93)
```

### 合并判断

```
Segment 1 → Segment 2:
  - 场景一致: meeting ✓
  - 时间间隔: 5分钟 < 10分钟 ✓
  - 可合并 ✓

Segment 2 → Segment 3:
  - 场景一致: meeting ✓
  - 时间间隔: 10分钟 = 10分钟 ✓
  - 可合并 ✓

Segment 3 → Segment 4:
  - 场景一致: meeting ✓
  - 时间间隔: 3分钟 < 10分钟 ✓
  - 可合并 ✓

合并后总时长: 102分钟 < 120分钟 ✓
```

### 输出

```
MergedSegment:
  id: "merged-seg1-seg2-seg3-seg4"
  scene: meeting
  start_time: 0
  end_time: 7200
  duration: 7200
  original_segment_ids: ["seg1", "seg2", "seg3", "seg4"]
  gap_durations: [300, 600, 180]  # 5分钟, 10分钟, 3分钟
  confidence: 0.935  # 平均值
```

### 分析结果

```markdown
# 项目进度会议

**时间**: 00:00 - 02:00 (2小时)
**说话人**: SPEAKER_00, SPEAKER_01, SPEAKER_02

## 摘要
讨论了项目整体进度,包括后端开发、前端设计、接口联调安排,以及新增的数据导出需求。

## 议程
1. 后端进度汇报 (00:00-00:25)
2. 前端进度汇报 (00:30-00:55)
3. 技术方案讨论 (01:05-01:35)
4. 决策与待办事项 (01:38-02:00)

## 关键要点
- 后端认证模块完成,下周三性能测试
- 前端80%完成,下周一交付
- 下周四开始接口联调
- 新增数据导出功能需求

## 待办事项
- [SPEAKER_01] 准备接口文档和测试环境 (2026-03-06)
- [SPEAKER_02] 评估数据导出功能工作量 (2026-03-02)

## 元数据
- 原始片段: 4个
- 茶歇间隔: 5分钟, 10分钟, 3分钟
```

---

## 实现优先级

### Phase 1 (MVP)
- [x] 基础 Segmenter 实现
- [x] 场景分类器
- [ ] **SegmentMerger 核心逻辑**
- [ ] **Pipeline 集成**

### Phase 2 (优化)
- [ ] 场景特定合并策略优化
- [ ] 合并质量评估指标
- [ ] 支持跨 chunk 合并

### Phase 3 (高级)
- [ ] 基于 LLM 的智能合并决策
- [ ] 用户反馈学习机制

---

## 测试策略

### 单元测试

```python
def test_merge_consecutive_meetings():
    """测试连续会议片段合并。"""
    seg1 = ClassifiedSegment(scene=SceneType.MEETING, start_time=0, end_time=1500, ...)
    seg2 = ClassifiedSegment(scene=SceneType.MEETING, start_time=1800, end_time=3300, ...)

    merger = SegmentMerger(config)
    result = merger.merge([seg1, seg2])

    assert len(result) == 1
    assert isinstance(result[0], MergedSegment)
    assert result[0].duration == 3300

def test_no_merge_different_scenes():
    """测试不同场景不合并。"""
    seg1 = ClassifiedSegment(scene=SceneType.MEETING, ...)
    seg2 = ClassifiedSegment(scene=SceneType.PHONE, ...)

    merger = SegmentMerger(config)
    result = merger.merge([seg1, seg2])

    assert len(result) == 2

def test_no_merge_large_gap():
    """测试间隔过大不合并。"""
    seg1 = ClassifiedSegment(scene=SceneType.MEETING, start_time=0, end_time=1500, ...)
    seg2 = ClassifiedSegment(scene=SceneType.MEETING, start_time=2200, end_time=3700, ...)
    # 间隔 700秒 > 600秒

    merger = SegmentMerger(config)
    result = merger.merge([seg1, seg2])

    assert len(result) == 2
```

### 集成测试

```python
async def test_pipeline_with_merger():
    """测试完整 Pipeline 包含合并逻辑。"""
    # 准备测试音频(包含茶歇的长会议)
    audio_path = "test_data/long_meeting_with_breaks.wav"

    pipeline = Pipeline(config)
    results = await pipeline.process(audio_path)

    # 验证合并效果
    assert len(results) == 1  # 应该合并为1个结果
    assert "茶歇" in results[0].metadata  # 元数据中记录了茶歇信息
```

---

## 配置建议

### 默认配置 (适用于大多数场景)

```yaml
segmenter:
  min_silence_gap: 300  # 5分钟

merger:
  enabled: true
  max_gap_between_segments: 600  # 10分钟
  max_merged_duration: 7200  # 2小时
  mergeable_scenes:
    - meeting
    - learning
    - business
```

### 严格模式 (避免误合并)

```yaml
merger:
  enabled: true
  max_gap_between_segments: 300  # 5分钟
  max_merged_duration: 3600  # 1小时
  mergeable_scenes:
    - meeting  # 仅合并会议
```

### 宽松模式 (最大化合并)

```yaml
merger:
  enabled: true
  max_gap_between_segments: 900  # 15分钟
  max_merged_duration: 10800  # 3小时
  mergeable_scenes:
    - meeting
    - learning
    - business
    - phone
```

---

## 注意事项

1. **跨 chunk 合并**: 当前设计仅在单个 chunk 内合并。如果会议跨越多个 chunk,需要在更高层实现合并逻辑(Phase 2)。

2. **说话人一致性**: 合并后的 MergedSegment 可能包含来自不同 chunk 的说话人 ID,需要在分析时注意。

3. **性能影响**: 合并会增加单次 LLM 调用的输入长度,可能影响响应时间和成本。

4. **用户控制**: 建议在归档时保留原始 Segment 信息,允许用户查看合并前的细节。

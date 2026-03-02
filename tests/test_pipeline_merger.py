from __future__ import annotations

import asyncio
from pathlib import Path

from audio_journal.config import load_config
from audio_journal.models.schemas import (
    AnalysisResult,
    ClassifiedSegment,
    MergedSegment,
    SceneType,
    Segment,
    Speaker,
    Utterance,
)
from audio_journal.pipeline import Pipeline


class _FakeChunker:
    def split(self, audio_path: str | Path, output_dir: str | Path):
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        p = out_dir / "chunk_001.wav"
        p.write_bytes(b"x")
        return [type("C", (), {"path": p})()]


class _FakeASR:
    def transcribe(self, audio_path: str):
        return [
            Utterance(
                speaker=Speaker(id="SPEAKER_00"),
                text="meeting part 1",
                start_time=0.0,
                end_time=1500.0,
            ),
            Utterance(
                speaker=Speaker(id="SPEAKER_01"),
                text="meeting part 2",
                start_time=1800.0,
                end_time=3300.0,
            ),
        ]


class _FakeSegmenter:
    """返回两个相邻的 meeting 片段，间隔 300 秒（5 分钟）。"""

    def segment(self, utterances, source_file: str):
        seg1 = Segment(
            id="seg-1",
            utterances=[utterances[0]],
            start_time=0.0,
            end_time=1500.0,
            duration=1500.0,
            source_file=source_file,
        )
        seg2 = Segment(
            id="seg-2",
            utterances=[utterances[1]],
            start_time=1800.0,
            end_time=3300.0,
            duration=1500.0,
            source_file=source_file,
        )
        return [seg1, seg2]


class _FakeClassifier:
    """将所有片段分类为 meeting。"""

    async def classify(self, seg: Segment) -> ClassifiedSegment:
        return ClassifiedSegment(
            **seg.model_dump(),
            scene=SceneType.MEETING,
            confidence=0.9,
            value_tags=[],
        )


class _FakeMeetingAnalyzer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def analyze(self, seg: ClassifiedSegment | MergedSegment) -> AnalysisResult:
        self.calls.append(seg.id)
        return AnalysisResult(
            segment_id=seg.id,
            scene=seg.scene,
            summary="meeting analysis",
            raw_text="x",
        )


class _FakeArchiver:
    def __init__(self) -> None:
        self.archived: list[AnalysisResult] = []

    def archive_all(self, results, *, source_file: str = ""):
        self.archived.extend(results)
        return []


def test_pipeline_with_merger_enabled(tmp_path: Path) -> None:
    """测试启用 merger 时，相邻 meeting 片段会被合并。"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"""
paths:
  processing: {tmp_path.as_posix()}/processing
  prompts: {tmp_path.as_posix()}/prompts
archive:
  default_target: local
  local:
    base_dir: {tmp_path.as_posix()}/archive
merger:
  enabled: true
  max_gap_between_segments: 600
  max_merged_duration: 7200
  mergeable_scenes:
    - meeting
    - learning
    - business
""".lstrip(),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)

    meeting_analyzer = _FakeMeetingAnalyzer()
    archiver = _FakeArchiver()

    pipe = Pipeline(
        cfg,
        chunker=_FakeChunker(),
        asr=_FakeASR(),
        segmenter=_FakeSegmenter(),
        classifier=_FakeClassifier(),
        meeting_analyzer=meeting_analyzer,
        archiver=archiver,
    )

    audio = tmp_path / "in.wav"
    audio.write_bytes(b"x")

    results = asyncio.run(pipe.process(audio))

    # 应该只有 1 个结果（两个片段被合并）
    assert len(results) == 1
    # 分析器应该只被调用一次，且传入的是合并后的片段
    assert len(meeting_analyzer.calls) == 1
    assert meeting_analyzer.calls[0] == "merged-seg-1-seg-2"
    # 归档应该只有 1 个结果
    assert len(archiver.archived) == 1


def test_pipeline_with_merger_disabled(tmp_path: Path) -> None:
    """测试禁用 merger 时，片段不会被合并。"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"""
paths:
  processing: {tmp_path.as_posix()}/processing
  prompts: {tmp_path.as_posix()}/prompts
archive:
  default_target: local
  local:
    base_dir: {tmp_path.as_posix()}/archive
merger:
  enabled: false
""".lstrip(),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)

    meeting_analyzer = _FakeMeetingAnalyzer()
    archiver = _FakeArchiver()

    pipe = Pipeline(
        cfg,
        chunker=_FakeChunker(),
        asr=_FakeASR(),
        segmenter=_FakeSegmenter(),
        classifier=_FakeClassifier(),
        meeting_analyzer=meeting_analyzer,
        archiver=archiver,
    )

    audio = tmp_path / "in.wav"
    audio.write_bytes(b"x")

    results = asyncio.run(pipe.process(audio))

    # 应该有 2 个结果（片段未合并）
    assert len(results) == 2
    # 分析器应该被调用两次
    assert len(meeting_analyzer.calls) == 2
    assert meeting_analyzer.calls == ["seg-1", "seg-2"]
    # 归档应该有 2 个结果
    assert len(archiver.archived) == 2

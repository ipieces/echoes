from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from audio_journal.analyzer.base import render_transcript
from audio_journal.analyzer.meeting import MeetingAnalyzer
from audio_journal.archiver.local import LocalArchiver
from audio_journal.asr.base import ASREngine
from audio_journal.asr.mock import MockASREngine
from audio_journal.chunker.vad_chunker import VADChunker
from audio_journal.classifier.scene import SceneClassifier
from audio_journal.config import AppConfig
from audio_journal.llm.base import LLMFactory
from audio_journal.merger.segment_merger import SegmentMerger
from audio_journal.models.schemas import (
    AnalysisResult,
    ClassifiedSegment,
    MergedSegment,
    SceneType,
)
from audio_journal.segmenter.silence import SilenceSegmenter


class PassthroughAnalyzer:
    """不调用 LLM，仅保留 transcript + scene。"""

    async def analyze(self, segment: ClassifiedSegment | MergedSegment) -> AnalysisResult:
        return AnalysisResult(
            segment_id=segment.id,
            scene=segment.scene,
            raw_text=render_transcript(segment.utterances),
            metadata={
                "confidence": segment.confidence,
                "value_tags": segment.value_tags,
            },
        )


class Pipeline:
    """核心处理 Pipeline（Phase 1 MVP）。"""

    def __init__(
        self,
        config: AppConfig,
        *,
        chunker: Optional[VADChunker] = None,
        asr: Optional[ASREngine] = None,
        segmenter: Optional[SilenceSegmenter] = None,
        classifier: Optional[SceneClassifier] = None,
        merger: Optional[SegmentMerger] = None,
        meeting_analyzer: Optional[MeetingAnalyzer] = None,
        archiver: Optional[LocalArchiver] = None,
    ) -> None:
        self.config = config
        self.chunker = chunker or VADChunker(config.chunker)
        self.asr = asr or _default_asr(config)
        self.segmenter = segmenter or SilenceSegmenter(config.segmenter)
        self.classifier = classifier or _default_classifier(config)
        self.merger = merger or SegmentMerger(config.merger)
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
            # 归档侧需要知道原始音频文件名；不要传 chunk 文件名。
            segments = self.segmenter.segment(utterances, source_file=str(src.name))

            classified: list[ClassifiedSegment] = []
            for seg in segments:
                classified.append(await self.classifier.classify(seg))

            # 合并 (新增)
            if self.config.merger.enabled:
                merged_segments = self.merger.merge(classified)
            else:
                merged_segments = classified

            for seg in merged_segments:
                if seg.scene == SceneType.MEETING:
                    res = await self.meeting_analyzer.analyze(seg)
                else:
                    res = await self.passthrough_analyzer.analyze(seg)
                all_results.append(res)

        # Phase 1：自动本地归档
        self.archiver.archive_all(all_results, source_file=str(src.name))
        return all_results


def _default_asr(config: AppConfig) -> ASREngine:
    if config.asr.engine == "mock":
        fixture = Path(os.getenv("AUDIO_JOURNAL_MOCK_ASR_FIXTURE", ""))
        if not fixture.exists():
            raise RuntimeError("使用 mock ASR 时需要设置 AUDIO_JOURNAL_MOCK_ASR_FIXTURE")
        return MockASREngine(fixture)
    elif config.asr.engine == "funasr":
        # 延迟导入，避免在 mock 模式下加载 FunASR 依赖
        try:
            from audio_journal.asr.funasr import FunASREngine
        except ImportError as e:
            raise RuntimeError(
                "FunASR 引擎需要额外依赖。请运行: pip install funasr modelscope"
            ) from e
        return FunASREngine(config.asr, model_dir=config.asr.model_dir)
    else:
        raise NotImplementedError(
            f"ASR engine '{config.asr.engine}' 未实现。支持的引擎: mock, funasr"
        )


def _default_classifier(config: AppConfig) -> SceneClassifier:
    llm = LLMFactory.create(config.llm, stage="classifier")
    return SceneClassifier(prompt_path=config.paths.prompts / "classifier.txt", llm=llm)


def _default_meeting_analyzer(config: AppConfig) -> MeetingAnalyzer:
    llm = LLMFactory.create(config.llm, stage="analyzer")
    return MeetingAnalyzer(llm=llm, prompt_path=config.paths.prompts / "meeting.txt")

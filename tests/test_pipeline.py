from __future__ import annotations

import asyncio
from pathlib import Path

from audio_journal.config import load_config
from audio_journal.models.schemas import (
    AnalysisResult,
    ClassifiedSegment,
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
                text="hi",
                start_time=0.0,
                end_time=1.0,
            ),
            Utterance(
                speaker=Speaker(id="SPEAKER_01"),
                text="ok",
                start_time=1.1,
                end_time=2.0,
            ),
        ]


class _FakeSegmenter:
    def segment(self, utterances, source_file: str):
        seg1 = Segment(
            id="seg-1",
            utterances=utterances,
            start_time=0.0,
            end_time=2.0,
            duration=2.0,
            source_file=source_file,
        )
        seg2 = Segment(
            id="seg-2",
            utterances=utterances,
            start_time=2.0,
            end_time=4.0,
            duration=2.0,
            source_file=source_file,
        )
        return [seg1, seg2]


class _FakeClassifier:
    async def classify(self, seg: Segment) -> ClassifiedSegment:
        scene = SceneType.MEETING if seg.id == "seg-1" else SceneType.PHONE
        return ClassifiedSegment(
            **seg.model_dump(),
            scene=scene,
            confidence=0.9,
            value_tags=[],
        )


class _FakeMeetingAnalyzer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def analyze(self, seg: ClassifiedSegment) -> AnalysisResult:
        self.calls.append(seg.id)
        return AnalysisResult(
            segment_id=seg.id,
            scene=seg.scene,
            summary="meeting",
            raw_text="x",
        )


class _FakeArchiver:
    def __init__(self) -> None:
        self.archived: list[AnalysisResult] = []

    def archive_all(self, results, *, source_file: str = ""):
        self.archived.extend(results)
        return []


def test_pipeline_happy_path_with_fakes(tmp_path: Path) -> None:
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

    assert len(results) == 2
    assert meeting_analyzer.calls == ["seg-1"]
    # 非 meeting 场景走 passthrough，不会有 summary
    assert any(r.segment_id == "seg-2" and r.summary == "" for r in results)
    assert len(archiver.archived) == 2


def test_pipeline_process_multi_chunk_uses_original_source_file(tmp_path: Path) -> None:
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
""".lstrip(),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)

    class _FakeChunkerMulti:
        def split(self, audio_path: str | Path, output_dir: str | Path):
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            p1 = out_dir / "chunk_001.wav"
            p2 = out_dir / "chunk_002.wav"
            p1.write_bytes(b"x")
            p2.write_bytes(b"y")
            C = type("C", (), {})
            c1 = C()
            c1.path = p1
            c2 = C()
            c2.path = p2
            return [c1, c2]

    class _FakeASRByChunk:
        def transcribe(self, audio_path: str):
            text = "hi-1" if "chunk_001" in audio_path else "hi-2"
            return [
                Utterance(
                    speaker=Speaker(id="SPEAKER_00"),
                    text=text,
                    start_time=0.0,
                    end_time=1.0,
                )
            ]

    class _FakeSegmenterCapture:
        def __init__(self) -> None:
            self.source_files: list[str] = []

        def segment(self, utterances, source_file: str):
            self.source_files.append(source_file)
            seg = Segment(
                id=f"seg-{utterances[0].text}",
                utterances=utterances,
                start_time=0.0,
                end_time=1.0,
                duration=1.0,
                source_file=source_file,
            )
            return [seg]

    class _FakeClassifier2:
        async def classify(self, seg: Segment) -> ClassifiedSegment:
            scene = SceneType.MEETING if seg.id == "seg-hi-1" else SceneType.PHONE
            return ClassifiedSegment(
                **seg.model_dump(),
                scene=scene,
                confidence=0.9,
                value_tags=[],
            )

    class _FakeMeetingAnalyzer2:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def analyze(self, seg: ClassifiedSegment) -> AnalysisResult:
            self.calls.append(seg.id)
            return AnalysisResult(
                segment_id=seg.id,
                scene=seg.scene,
                summary="meeting",
                raw_text="x",
            )

    class _FakeArchiver2:
        def __init__(self) -> None:
            self.source_file: str | None = None

        def archive_all(self, results, *, source_file: str = ""):
            self.source_file = source_file
            return []

    segmenter = _FakeSegmenterCapture()
    meeting_analyzer = _FakeMeetingAnalyzer2()
    archiver = _FakeArchiver2()

    pipe = Pipeline(
        cfg,
        chunker=_FakeChunkerMulti(),
        asr=_FakeASRByChunk(),
        segmenter=segmenter,
        classifier=_FakeClassifier2(),
        meeting_analyzer=meeting_analyzer,
        archiver=archiver,
    )

    audio = tmp_path / "in.wav"
    audio.write_bytes(b"x")

    results = asyncio.run(pipe.process(audio))

    assert len(results) == 2
    assert meeting_analyzer.calls == ["seg-hi-1"]
    assert segmenter.source_files == ["in.wav", "in.wav"]
    assert archiver.source_file == "in.wav"

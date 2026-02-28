#!/usr/bin/env python3
"""Audio Journal Integration Test — tests each pipeline stage independently."""

import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from audio_journal.asr.mock import MockASREngine
from audio_journal.chunker.vad_chunker import VADChunker
from audio_journal.config import load_config
from audio_journal.models.schemas import AnalysisResult, ClassifiedSegment, SceneType
from audio_journal.segmenter.silence import SilenceSegmenter
from audio_journal.archiver.local import LocalArchiver
from audio_journal.classifier.scene import SceneClassifier


class MockLLMProvider:
    """Mock LLM that returns heuristic-based classification."""

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        p = prompt
        if "会议" in p or "项目进度" in p or "联调" in p:
            return json.dumps({"scene": "meeting", "confidence": 0.85})
        elif "快递" in p or "喂" in p or "电话" in p:
            return json.dumps({"scene": "phone", "confidence": 0.80})
        elif "日记" in p or "想法" in p or "思考" in p:
            return json.dumps({"scene": "idea", "confidence": 0.75})
        return json.dumps({"scene": "chat", "confidence": 0.60})


class MockMeetingAnalyzer:
    """Mock meeting analyzer."""

    async def analyze(self, seg: ClassifiedSegment) -> AnalysisResult:
        transcript = "\n".join(
            f"[{u.start_time:.1f}s] {u.speaker.id}: {u.text}" for u in seg.utterances
        )
        return AnalysisResult(
            segment_id=seg.id,
            scene=seg.scene,
            summary="项目进度讨论会议，涉及后端开发、前端进度和接口联调安排。",
            key_points=[
                "后端用户认证模块已完成，正在进行数据库优化",
                "前端核心页面完成80%，下周一交付第一版",
                "计划下周四开始接口联调",
                "客户提出新需求：数据导出功能",
            ],
            action_items=[
                "张工：准备接口文档和测试环境 [下周四]",
                "李工：评估数据导出功能工作量 [明天]",
            ],
            participants=["王总", "张工", "李工"],
            topics=["项目进度", "接口联调", "新需求"],
            raw_text=transcript,
            metadata={"test_mode": True},
        )


class Results:
    def __init__(self):
        self.rows: list[dict] = []
        self.t0 = time.time()

    def add(self, stage: str, status: str, detail: str = "", dur: float = 0.0):
        self.rows.append(dict(stage=stage, status=status, detail=detail, dur=dur))

    def summary(self) -> str:
        lines = ["\n" + "=" * 70, "TEST SUMMARY", "=" * 70]
        for r in self.rows:
            icon = "✅" if r["status"] == "PASS" else "❌"
            lines.append(f"\n{icon} {r['stage']}: {r['status']}")
            if r["detail"]:
                lines.append(f"   {r['detail']}")
            if r["dur"] > 0:
                lines.append(f"   Duration: {r['dur']:.3f}s")
        passed = sum(1 for r in self.rows if r["status"] == "PASS")
        total = len(self.rows)
        elapsed = time.time() - self.t0
        lines += ["", "=" * 70, f"Total: {passed}/{total} passed | {elapsed:.2f}s", "=" * 70]
        return "\n".join(lines)


SCENARIOS = [
    ("scenario1_meeting", "fixture_meeting.json", "工作会议"),
    ("scenario2_phone", "fixture_phone.json", "电话对话"),
    ("scenario3_monologue", "fixture_monologue.json", "个人独白"),
]


async def run_all():
    base = Path(__file__).parent.parent
    os.chdir(base)

    cfg = load_config(Path("config.yaml"))
    res = Results()

    # ── Stage 1: Chunker ──
    for name, _, label in SCENARIOS:
        wav = Path(f"test_data/{name}.wav")
        if not wav.exists():
            res.add(f"Chunker/{label}", "FAIL", f"WAV not found: {wav}")
            continue
        t0 = time.time()
        try:
            chunker = VADChunker(cfg.chunker)
            out_dir = Path(f"test_results/chunks/{name}")
            out_dir.mkdir(parents=True, exist_ok=True)
            chunks = chunker.split(wav, out_dir)
            dur = time.time() - t0
            total_dur = sum(c.duration for c in chunks)
            res.add(f"Chunker/{label}", "PASS",
                     f"{len(chunks)} chunks, total {total_dur:.1f}s", dur)
        except Exception as e:
            res.add(f"Chunker/{label}", "FAIL", str(e), time.time() - t0)

    # ── Stage 2: Mock ASR ──
    all_utterances = {}
    for name, fixture, label in SCENARIOS:
        fixture_path = Path(f"test_data/{fixture}")
        t0 = time.time()
        try:
            asr = MockASREngine(fixture_path)
            utts = asr.transcribe("dummy.wav")
            speakers = sorted(set(u.speaker.id for u in utts))
            all_utterances[name] = utts
            dur = time.time() - t0
            res.add(f"ASR/{label}", "PASS",
                     f"{len(utts)} utterances, speakers: {speakers}", dur)
        except Exception as e:
            res.add(f"ASR/{label}", "FAIL", str(e), time.time() - t0)

    # ── Stage 3: Segmenter ──
    all_segments = {}
    for name, _, label in SCENARIOS:
        utts = all_utterances.get(name)
        if not utts:
            res.add(f"Segmenter/{label}", "FAIL", "No utterances from ASR")
            continue
        t0 = time.time()
        try:
            segmenter = SilenceSegmenter(cfg.segmenter)
            segs = segmenter.segment(utts, source_file=f"{name}.wav")
            all_segments[name] = segs
            dur = time.time() - t0
            seg_info = ", ".join(f"{s.id}({s.duration:.1f}s)" for s in segs)
            res.add(f"Segmenter/{label}", "PASS",
                     f"{len(segs)} segments: {seg_info}", dur)
        except Exception as e:
            res.add(f"Segmenter/{label}", "FAIL", str(e), time.time() - t0)

    # ── Stage 4: Classifier (Mock LLM) ──
    mock_llm = MockLLMProvider()
    all_classified = {}
    for name, _, label in SCENARIOS:
        segs = all_segments.get(name)
        if not segs:
            res.add(f"Classifier/{label}", "FAIL", "No segments")
            continue
        t0 = time.time()
        try:
            prompt_path = Path("prompts/classifier.txt")
            classifier = SceneClassifier(prompt_path=prompt_path, llm=mock_llm)
            classified = []
            for seg in segs:
                c = await classifier.classify(seg)
                classified.append(c)
            all_classified[name] = classified
            dur = time.time() - t0
            cls_info = ", ".join(f"{c.scene.value}({c.confidence:.2f})" for c in classified)
            res.add(f"Classifier/{label}", "PASS", f"Scenes: {cls_info}", dur)
        except Exception as e:
            res.add(f"Classifier/{label}", "FAIL", str(e), time.time() - t0)

    # ── Stage 5: Analyzer (Mock) ──
    mock_analyzer = MockMeetingAnalyzer()
    all_analysis = {}
    for name, _, label in SCENARIOS:
        classified = all_classified.get(name)
        if not classified:
            res.add(f"Analyzer/{label}", "FAIL", "No classified segments")
            continue
        t0 = time.time()
        try:
            analysis_results = []
            for seg in classified:
                if seg.scene == SceneType.MEETING:
                    ar = await mock_analyzer.analyze(seg)
                else:
                    from audio_journal.analyzer.base import render_transcript
                    ar = AnalysisResult(
                        segment_id=seg.id,
                        scene=seg.scene,
                        raw_text=render_transcript(seg.utterances),
                        metadata={"confidence": seg.confidence},
                    )
                analysis_results.append(ar)
            all_analysis[name] = analysis_results
            dur = time.time() - t0
            res.add(f"Analyzer/{label}", "PASS",
                     f"{len(analysis_results)} results", dur)
        except Exception as e:
            res.add(f"Analyzer/{label}", "FAIL", str(e), time.time() - t0)

    # ── Stage 6: Archiver ──
    archive_dir = Path("test_results/archive")
    archive_dir.mkdir(parents=True, exist_ok=True)
    for name, _, label in SCENARIOS:
        ars = all_analysis.get(name)
        if not ars:
            res.add(f"Archiver/{label}", "FAIL", "No analysis results")
            continue
        t0 = time.time()
        try:
            archiver = LocalArchiver(base_dir=archive_dir)
            entries = archiver.archive_all(ars, source_file=f"{name}.wav")
            dur = time.time() - t0
            entry_info = ", ".join(f"{e.id}({e.scene.value})" for e in entries)
            res.add(f"Archiver/{label}", "PASS",
                     f"{len(entries)} entries: {entry_info}", dur)
        except Exception as e:
            res.add(f"Archiver/{label}", "FAIL", str(e), time.time() - t0)

    # ── Stage 7: Full Pipeline (Mock) ──
    for name, fixture, label in SCENARIOS:
        wav = Path(f"test_data/{name}.wav")
        fixture_path = Path(f"test_data/{fixture}")
        if not wav.exists():
            res.add(f"Pipeline/{label}", "FAIL", "WAV not found")
            continue
        t0 = time.time()
        try:
            from audio_journal.pipeline import Pipeline, PassthroughAnalyzer
            os.environ["AUDIO_JOURNAL_MOCK_ASR_FIXTURE"] = str(fixture_path)
            pipe = Pipeline(
                cfg,
                asr=MockASREngine(fixture_path),
                classifier=SceneClassifier(prompt_path=Path("prompts/classifier.txt"), llm=mock_llm),
                meeting_analyzer=mock_analyzer,
                archiver=LocalArchiver(base_dir=Path("test_results/pipeline_archive")),
            )
            results = await pipe.process(wav)
            dur = time.time() - t0
            res.add(f"Pipeline/{label}", "PASS",
                     f"{len(results)} results archived", dur)
        except Exception as e:
            dur = time.time() - t0
            res.add(f"Pipeline/{label}", "FAIL", str(e), dur)

    summary = res.summary()
    print(summary)
    return res


if __name__ == "__main__":
    res = asyncio.run(run_all())

from __future__ import annotations

import json
from pathlib import Path

from audio_journal.analyzer.learning import LearningAnalyzer
from audio_journal.models.schemas import ClassifiedSegment, SceneType, Segment, Speaker, Utterance


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        return self.reply


def _learning_segment() -> ClassifiedSegment:
    utterances = [
        Utterance(speaker=Speaker(id="SPEAKER_00"), text="学到了新知识", start_time=0.0, end_time=1.0),
        Utterance(speaker=Speaker(id="SPEAKER_00"), text="来自某个课程", start_time=1.2, end_time=2.0),
    ]
    seg = Segment(
        id="seg-1",
        utterances=utterances,
        start_time=0.0,
        end_time=2.0,
        duration=2.0,
        source_file="a.wav",
    )
    return ClassifiedSegment(**seg.model_dump(), scene=SceneType.LEARNING, confidence=0.9, value_tags=[])


def test_learning_analyzer_parses_json_to_result(tmp_path: Path) -> None:
    prompt_path = tmp_path / "learning.txt"
    prompt_path.write_text(
        """{{start_time}}-{{end_time}}\n{{speakers}}\n{{transcript}}""",
        encoding="utf-8",
    )

    llm_reply = json.dumps(
        {
            "summary": "学习了 Python 异步编程",
            "knowledge_points": ["asyncio 基础", "协程概念"],
            "sources": ["Real Python 课程"],
            "key_takeaways": ["异步提升性能"],
            "further_reading": ["深入理解事件循环"],
            "topics": ["Python", "异步"],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = LearningAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _learning_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))

    assert out.segment_id == "seg-1"
    assert out.scene == SceneType.LEARNING
    assert out.summary == "学习了 Python 异步编程"
    assert out.key_points == ["异步提升性能"]
    assert "延伸阅读: 深入理解事件循环" in out.action_items
    assert out.raw_text


def test_learning_analyzer_puts_knowledge_points_in_metadata(tmp_path: Path) -> None:
    prompt_path = tmp_path / "learning.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    llm_reply = json.dumps(
        {
            "summary": "s",
            "knowledge_points": ["k1", "k2"],
            "sources": ["src1"],
            "key_takeaways": ["t1"],
            "further_reading": ["f1"],
            "topics": [],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = LearningAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _learning_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))
    assert out.metadata["knowledge_points"] == ["k1", "k2"]
    assert out.metadata["sources"] == ["src1"]
    assert out.metadata["further_reading"] == ["f1"]

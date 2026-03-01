from __future__ import annotations

import json
from pathlib import Path

from audio_journal.analyzer.chat import ChatAnalyzer
from audio_journal.models.schemas import ClassifiedSegment, SceneType, Segment, Speaker, Utterance


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        return self.reply


def _chat_segment() -> ClassifiedSegment:
    utterances = [
        Utterance(speaker=Speaker(id="SPEAKER_00"), text="最近市场怎么样", start_time=0.0, end_time=1.0),
        Utterance(speaker=Speaker(id="SPEAKER_01"), text="有个投资机会", start_time=1.2, end_time=2.0),
    ]
    seg = Segment(
        id="seg-1",
        utterances=utterances,
        start_time=0.0,
        end_time=2.0,
        duration=2.0,
        source_file="a.wav",
    )
    return ClassifiedSegment(**seg.model_dump(), scene=SceneType.CHAT, confidence=0.9, value_tags=[])


def test_chat_analyzer_parses_json_to_result(tmp_path: Path) -> None:
    prompt_path = tmp_path / "chat.txt"
    prompt_path.write_text(
        """{{start_time}}-{{end_time}}\n{{speakers}}\n{{transcript}}""",
        encoding="utf-8",
    )

    llm_reply = json.dumps(
        {
            "summary": "讨论投资机会",
            "all_topics": ["市场", "投资", "天气"],
            "high_value_topics": ["投资机会"],
            "topic_categories": ["investment"],
            "key_insights": ["某行业有增长潜力"],
            "value_score": 0.75,
            "topics": ["投资", "市场"],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = ChatAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _chat_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))

    assert out.segment_id == "seg-1"
    assert out.scene == SceneType.CHAT
    assert out.summary == "讨论投资机会"
    assert out.key_points == ["某行业有增长潜力"]
    assert out.value_level == "high"  # score 0.75 >= 0.6
    assert out.raw_text


def test_chat_analyzer_calculates_value_level(tmp_path: Path) -> None:
    prompt_path = tmp_path / "chat.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    # Test high value
    llm_reply = json.dumps(
        {
            "summary": "s",
            "all_topics": [],
            "high_value_topics": [],
            "topic_categories": [],
            "key_insights": [],
            "value_score": 0.8,
            "topics": [],
        }
    )
    llm = _FakeLLM(llm_reply)
    analyzer = ChatAnalyzer(llm=llm, prompt_path=prompt_path)
    out = __import__("asyncio").run(analyzer.analyze(_chat_segment()))
    assert out.value_level == "high"

    # Test medium value
    llm_reply = json.dumps(
        {
            "summary": "s",
            "all_topics": [],
            "high_value_topics": [],
            "topic_categories": [],
            "key_insights": [],
            "value_score": 0.4,
            "topics": [],
        }
    )
    llm = _FakeLLM(llm_reply)
    analyzer = ChatAnalyzer(llm=llm, prompt_path=prompt_path)
    out = __import__("asyncio").run(analyzer.analyze(_chat_segment()))
    assert out.value_level == "medium"

    # Test low value
    llm_reply = json.dumps(
        {
            "summary": "s",
            "all_topics": [],
            "high_value_topics": [],
            "topic_categories": [],
            "key_insights": [],
            "value_score": 0.2,
            "topics": [],
        }
    )
    llm = _FakeLLM(llm_reply)
    analyzer = ChatAnalyzer(llm=llm, prompt_path=prompt_path)
    out = __import__("asyncio").run(analyzer.analyze(_chat_segment()))
    assert out.value_level == "low"


def test_chat_analyzer_puts_value_data_in_metadata(tmp_path: Path) -> None:
    prompt_path = tmp_path / "chat.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    llm_reply = json.dumps(
        {
            "summary": "s",
            "all_topics": ["t1", "t2"],
            "high_value_topics": ["t1"],
            "topic_categories": ["investment"],
            "key_insights": ["i1"],
            "value_score": 0.7,
            "topics": [],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = ChatAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _chat_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))
    assert out.metadata["all_topics"] == ["t1", "t2"]
    assert out.metadata["high_value_topics"] == ["t1"]
    assert out.metadata["topic_categories"] == ["investment"]
    assert out.metadata["value_score"] == 0.7

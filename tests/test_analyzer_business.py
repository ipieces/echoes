from __future__ import annotations

import json
from pathlib import Path

from audio_journal.analyzer.business import BusinessAnalyzer
from audio_journal.models.schemas import ClassifiedSegment, SceneType, Segment, Speaker, Utterance


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        return self.reply


def _business_segment() -> ClassifiedSegment:
    utterances = [
        Utterance(speaker=Speaker(id="SPEAKER_00"), text="我们可以合作", start_time=0.0, end_time=1.0),
        Utterance(speaker=Speaker(id="SPEAKER_01"), text="好的，我会发资料", start_time=1.2, end_time=2.0),
    ]
    seg = Segment(
        id="seg-1",
        utterances=utterances,
        start_time=0.0,
        end_time=2.0,
        duration=2.0,
        source_file="a.wav",
    )
    return ClassifiedSegment(**seg.model_dump(), scene=SceneType.BUSINESS, confidence=0.9, value_tags=[])


def test_business_analyzer_parses_json_to_result(tmp_path: Path) -> None:
    prompt_path = tmp_path / "business.txt"
    prompt_path.write_text(
        """{{start_time}}-{{end_time}}\n{{speakers}}\n{{transcript}}""",
        encoding="utf-8",
    )

    llm_reply = json.dumps(
        {
            "summary": "商务合作讨论",
            "commitments": ["发送资料"],
            "follow_ups": ["安排会议"],
            "key_asks": ["提供案例"],
            "opportunities": ["潜在合作"],
            "participants": ["SPEAKER_00", "SPEAKER_01"],
            "topics": ["合作", "资料"],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = BusinessAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _business_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))

    assert out.segment_id == "seg-1"
    assert out.scene == SceneType.BUSINESS
    assert out.summary == "商务合作讨论"
    assert out.key_points == ["发送资料"]
    assert out.action_items == ["安排会议"]
    assert out.raw_text


def test_business_analyzer_puts_commitments_in_metadata(tmp_path: Path) -> None:
    prompt_path = tmp_path / "business.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    llm_reply = json.dumps(
        {
            "summary": "s",
            "commitments": ["c1", "c2"],
            "follow_ups": ["f1"],
            "key_asks": ["k1"],
            "opportunities": ["o1"],
            "participants": [],
            "topics": [],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = BusinessAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _business_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))
    assert out.metadata["commitments"] == ["c1", "c2"]
    assert out.metadata["follow_ups"] == ["f1"]
    assert out.metadata["key_asks"] == ["k1"]
    assert out.metadata["opportunities"] == ["o1"]

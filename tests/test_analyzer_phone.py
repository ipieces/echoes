from __future__ import annotations

import json
from pathlib import Path

from audio_journal.analyzer.phone import PhoneAnalyzer
from audio_journal.models.schemas import ClassifiedSegment, SceneType, Segment, Speaker, Utterance


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        return self.reply


def _phone_segment() -> ClassifiedSegment:
    utterances = [
        Utterance(speaker=Speaker(id="SPEAKER_00"), text="你好", start_time=0.0, end_time=1.0),
        Utterance(speaker=Speaker(id="SPEAKER_01"), text="我想确认一下", start_time=1.2, end_time=2.0),
    ]
    seg = Segment(
        id="seg-1",
        utterances=utterances,
        start_time=0.0,
        end_time=2.0,
        duration=2.0,
        source_file="a.wav",
    )
    return ClassifiedSegment(**seg.model_dump(), scene=SceneType.PHONE, confidence=0.9, value_tags=[])


def test_phone_analyzer_parses_json_to_result(tmp_path: Path) -> None:
    prompt_path = tmp_path / "phone.txt"
    prompt_path.write_text(
        """{{start_time}}-{{end_time}}\n{{speakers}}\n{{transcript}}""",
        encoding="utf-8",
    )

    llm_reply = json.dumps(
        {
            "summary": "确认会议时间",
            "caller_intent": "确认明天会议安排",
            "agreed_actions": ["明天下午2点开会"],
            "follow_up": "会前发送议程",
            "participants": ["SPEAKER_00", "SPEAKER_01"],
            "topics": ["会议", "确认"],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = PhoneAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _phone_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))

    assert out.segment_id == "seg-1"
    assert out.scene == SceneType.PHONE
    assert out.summary == "确认会议时间"
    assert "来电意图: 确认明天会议安排" in out.key_points
    assert "明天下午2点开会" in out.action_items
    assert "跟进: 会前发送议程" in out.action_items
    assert out.raw_text


def test_phone_analyzer_puts_caller_intent_in_metadata(tmp_path: Path) -> None:
    prompt_path = tmp_path / "phone.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    llm_reply = json.dumps(
        {
            "summary": "s",
            "caller_intent": "咨询产品",
            "agreed_actions": ["a1"],
            "follow_up": "下周联系",
            "participants": [],
            "topics": [],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = PhoneAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _phone_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))
    assert out.metadata["caller_intent"] == "咨询产品"
    assert out.metadata["agreed_actions"] == ["a1"]
    assert out.metadata["follow_up"] == "下周联系"

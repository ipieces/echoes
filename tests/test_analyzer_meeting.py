from __future__ import annotations

import json
from pathlib import Path

from audio_journal.analyzer.meeting import MeetingAnalyzer
from audio_journal.models.schemas import ClassifiedSegment, SceneType, Segment, Speaker, Utterance


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        return self.reply


def _meeting_segment() -> ClassifiedSegment:
    utterances = [
        Utterance(speaker=Speaker(id="SPEAKER_00"), text="开始", start_time=0.0, end_time=1.0),
        Utterance(speaker=Speaker(id="SPEAKER_01"), text="讨论", start_time=1.2, end_time=2.0),
    ]
    seg = Segment(
        id="seg-1",
        utterances=utterances,
        start_time=0.0,
        end_time=2.0,
        duration=2.0,
        source_file="a.wav",
    )
    return ClassifiedSegment(**seg.model_dump(), scene=SceneType.MEETING, confidence=0.9, value_tags=[])


def test_meeting_analyzer_parses_json_to_result(tmp_path: Path) -> None:
    prompt_path = tmp_path / "meeting.txt"
    prompt_path.write_text(
        """{{start_time}}-{{end_time}}\n{{speakers}}\n{{transcript}}""",
        encoding="utf-8",
    )

    llm_reply = json.dumps(
        {
            "summary": "s",
            "key_points": ["k1"],
            "decisions": ["d1"],
            "action_items": [{"task": "t", "owner": "SPEAKER_00", "deadline": None}],
            "participants": ["SPEAKER_00", "SPEAKER_01"],
            "topics": ["x"],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = MeetingAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _meeting_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))

    assert out.segment_id == "seg-1"
    assert out.scene == SceneType.MEETING
    assert out.summary == "s"
    assert out.key_points == ["k1"]
    assert out.action_items
    assert out.raw_text


def test_meeting_analyzer_puts_decisions_in_metadata(tmp_path: Path) -> None:
    prompt_path = tmp_path / "meeting.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    llm_reply = json.dumps(
        {
            "summary": "s",
            "key_points": [],
            "decisions": ["d1", "d2"],
            "action_items": [],
            "participants": [],
            "topics": [],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = MeetingAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _meeting_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))
    assert out.metadata["decisions"] == ["d1", "d2"]

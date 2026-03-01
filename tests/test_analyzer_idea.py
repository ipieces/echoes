from __future__ import annotations

import json
from pathlib import Path

from audio_journal.analyzer.idea import IdeaAnalyzer
from audio_journal.models.schemas import ClassifiedSegment, SceneType, Segment, Speaker, Utterance


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        return self.reply


def _idea_segment() -> ClassifiedSegment:
    utterances = [
        Utterance(speaker=Speaker(id="SPEAKER_00"), text="我有个想法", start_time=0.0, end_time=1.0),
        Utterance(speaker=Speaker(id="SPEAKER_00"), text="可以做个工具", start_time=1.2, end_time=2.0),
    ]
    seg = Segment(
        id="seg-1",
        utterances=utterances,
        start_time=0.0,
        end_time=2.0,
        duration=2.0,
        source_file="a.wav",
    )
    return ClassifiedSegment(**seg.model_dump(), scene=SceneType.IDEA, confidence=0.9, value_tags=[])


def test_idea_analyzer_parses_json_to_result(tmp_path: Path) -> None:
    prompt_path = tmp_path / "idea.txt"
    prompt_path.write_text(
        """{{start_time}}-{{end_time}}\n{{speakers}}\n{{transcript}}""",
        encoding="utf-8",
    )

    llm_reply = json.dumps(
        {
            "core_idea": "开发自动化工具",
            "idea_type": "plan",
            "related_topics": ["自动化", "工具"],
            "feasibility": "high",
            "next_steps": ["调研技术栈"],
            "topics": ["工具", "开发"],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = IdeaAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _idea_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))

    assert out.segment_id == "seg-1"
    assert out.scene == SceneType.IDEA
    assert out.summary == "开发自动化工具"
    assert "类型: plan" in out.key_points
    assert "可行性: high" in out.key_points
    assert out.action_items == ["调研技术栈"]
    assert out.raw_text


def test_idea_analyzer_puts_idea_type_in_metadata(tmp_path: Path) -> None:
    prompt_path = tmp_path / "idea.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    llm_reply = json.dumps(
        {
            "core_idea": "核心想法",
            "idea_type": "inspiration",
            "related_topics": ["t1", "t2"],
            "feasibility": "medium",
            "next_steps": [],
            "topics": [],
        }
    )
    llm = _FakeLLM(llm_reply)

    analyzer = IdeaAnalyzer(llm=llm, prompt_path=prompt_path)
    seg = _idea_segment()

    out = __import__("asyncio").run(analyzer.analyze(seg))
    assert out.metadata["idea_type"] == "inspiration"
    assert out.metadata["feasibility"] == "medium"
    assert out.metadata["related_topics"] == ["t1", "t2"]

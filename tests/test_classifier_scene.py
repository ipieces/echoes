from __future__ import annotations

from pathlib import Path

from audio_journal.classifier.scene import SceneClassifier
from audio_journal.models.schemas import SceneType, Segment, Speaker, Utterance


class _FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.last_prompt: str | None = None

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        self.last_prompt = prompt
        return self.reply


def _segment(n: int) -> Segment:
    utterances = [
        Utterance(
            speaker=Speaker(id="SPEAKER_00"),
            text=f"u{i}",
            start_time=float(i),
            end_time=float(i) + 0.5,
        )
        for i in range(n)
    ]
    return Segment(
        id="seg-1",
        utterances=utterances,
        start_time=0.0,
        end_time=float(n),
        duration=float(n),
        source_file="a.wav",
    )


def test_classifier_builds_prompt_sample(tmp_path: Path) -> None:
    prompt_path = tmp_path / "classifier.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    llm = _FakeLLM('{"scene":"meeting","confidence":0.9,"reasoning":"ok"}')
    clf = SceneClassifier(prompt_path=prompt_path, llm=llm, max_utterances=5)

    seg = _segment(20)

    out = __import__("asyncio").run(clf.classify(seg))
    assert out.scene == SceneType.MEETING

    assert llm.last_prompt is not None
    assert "u0" in llm.last_prompt
    assert "u4" in llm.last_prompt
    assert "u5" not in llm.last_prompt


def test_classifier_parses_llm_json(tmp_path: Path) -> None:
    prompt_path = tmp_path / "classifier.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    llm = _FakeLLM('{"scene":"phone","confidence":0.42,"reasoning":"ok"}')
    clf = SceneClassifier(prompt_path=prompt_path, llm=llm)

    seg = _segment(2)
    out = __import__("asyncio").run(clf.classify(seg))

    assert out.scene == SceneType.PHONE
    assert out.confidence == 0.42


def test_classifier_sets_empty_value_tags_in_mvp(tmp_path: Path) -> None:
    prompt_path = tmp_path / "classifier.txt"
    prompt_path.write_text("{{transcript}}", encoding="utf-8")

    llm = _FakeLLM('{"scene":"chat","confidence":0.7,"reasoning":"ok"}')
    clf = SceneClassifier(prompt_path=prompt_path, llm=llm)

    seg = _segment(2)
    out = __import__("asyncio").run(clf.classify(seg))

    assert out.scene == SceneType.CHAT
    assert out.value_tags == []

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from audio_journal.llm.base import LLMProvider
from audio_journal.models.schemas import ClassifiedSegment, Utterance


class BaseAnalyzer(ABC):
    """场景分析器抽象基类。"""

    def __init__(self, *, llm: LLMProvider, prompt_path: str | Path) -> None:
        self.llm = llm
        self.prompt_path = Path(prompt_path)
        self._prompt_template = self.prompt_path.read_text(encoding="utf-8")

    @abstractmethod
    async def analyze(self, segment: ClassifiedSegment):
        raise NotImplementedError

    def _render_prompt(self, *, transcript: str, start_time: str, end_time: str, speakers: str) -> str:
        prompt = self._prompt_template
        prompt = prompt.replace("{{transcript}}", transcript)
        prompt = prompt.replace("{{start_time}}", start_time)
        prompt = prompt.replace("{{end_time}}", end_time)
        prompt = prompt.replace("{{speakers}}", speakers)
        return prompt


def render_transcript(utterances: list[Utterance]) -> str:
    lines: list[str] = []
    for utt in utterances:
        ts = _format_hhmmss(utt.start_time)
        lines.append(f"[{ts}] {utt.speaker.id}: {utt.text}")
    return "\n".join(lines)


def _format_hhmmss(seconds: float) -> str:
    sec = max(0, int(seconds))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

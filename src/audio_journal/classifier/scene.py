from __future__ import annotations

from pathlib import Path

from audio_journal.llm.base import LLMProvider, parse_json_strict
from audio_journal.models.schemas import ClassifiedSegment, SceneType, Segment


class SceneClassifier:
    """场景分类器（Phase 1 仅做单层分类）。"""

    def __init__(self, *, prompt_path: str | Path, llm: LLMProvider, max_utterances: int = 12) -> None:
        self.prompt_path = Path(prompt_path)
        self.llm = llm
        self.max_utterances = max_utterances
        self._prompt_template = self.prompt_path.read_text(encoding="utf-8")

    async def classify(self, segment: Segment) -> ClassifiedSegment:
        transcript = self._extract_sample(segment)
        prompt = self._prompt_template.replace("{{transcript}}", transcript)

        text = await self.llm.complete(prompt, json_mode=True)
        data = parse_json_strict(text)

        scene_str = str(data.get("scene", "")).strip()
        confidence = float(data.get("confidence", 0.0))

        try:
            scene = SceneType(scene_str)
        except ValueError as e:
            raise ValueError(f"未知 scene: {scene_str!r}") from e

        return ClassifiedSegment(
            **segment.model_dump(),
            scene=scene,
            confidence=confidence,
            # Phase 1：不做 chat 的价值检测
            value_tags=[],
        )

    def _extract_sample(self, segment: Segment) -> str:
        """仅取前 N 条 utterances 构建 prompt 样本，避免超长输入。"""

        lines: list[str] = []
        for utt in segment.utterances[: self.max_utterances]:
            ts = _format_hhmmss(utt.start_time)
            lines.append(f"[{ts}] {utt.speaker.id}: {utt.text}")
        return "\n".join(lines)


def _format_hhmmss(seconds: float) -> str:
    sec = max(0, int(seconds))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

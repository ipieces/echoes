from __future__ import annotations

from typing import Any

from audio_journal.analyzer.base import BaseAnalyzer, render_transcript
from audio_journal.llm.base import parse_json_strict
from audio_journal.models.schemas import AnalysisResult, ClassifiedSegment, MergedSegment, SceneType


class IdeaAnalyzer(BaseAnalyzer):
    """想法记录分析器。"""

    async def analyze(self, segment: ClassifiedSegment | MergedSegment) -> AnalysisResult:
        if segment.scene != SceneType.IDEA:
            raise ValueError(f"IdeaAnalyzer 仅支持 idea，当前: {segment.scene}")

        transcript = render_transcript(segment.utterances)
        speakers = ", ".join(sorted({u.speaker.id for u in segment.utterances}))
        prompt = self._render_prompt(
            transcript=transcript,
            start_time=_format_mmss(segment.start_time),
            end_time=_format_mmss(segment.end_time),
            speakers=speakers,
        )

        text = await self.llm.complete(prompt, json_mode=True)
        data = parse_json_strict(text)

        core_idea = str(data.get("core_idea", ""))
        idea_type = str(data.get("idea_type", "unknown"))
        related_topics = list(data.get("related_topics", []) or [])
        feasibility = str(data.get("feasibility", "unknown"))
        next_steps = list(data.get("next_steps", []) or [])
        topics = list(data.get("topics", []) or [])

        metadata: dict[str, Any] = {
            "core_idea": core_idea,
            "idea_type": idea_type,
            "related_topics": related_topics,
            "feasibility": feasibility,
            "next_steps": next_steps,
        }

        return AnalysisResult(
            segment_id=segment.id,
            scene=segment.scene,
            summary=core_idea,
            key_points=[f"类型: {idea_type}", f"可行性: {feasibility}"],
            action_items=[str(x) for x in next_steps],
            topics=[str(x) for x in topics],
            raw_text=transcript,
            metadata=metadata,
        )


def _format_mmss(seconds: float) -> str:
    sec = max(0, int(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m:02d}:{s:02d}"

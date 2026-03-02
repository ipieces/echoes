from __future__ import annotations

from typing import Any

from audio_journal.analyzer.base import BaseAnalyzer, render_transcript
from audio_journal.llm.base import parse_json_strict
from audio_journal.models.schemas import AnalysisResult, ClassifiedSegment, MergedSegment, SceneType


class LearningAnalyzer(BaseAnalyzer):
    """学习记录分析器。"""

    async def analyze(self, segment: ClassifiedSegment | MergedSegment) -> AnalysisResult:
        if segment.scene != SceneType.LEARNING:
            raise ValueError(f"LearningAnalyzer 仅支持 learning，当前: {segment.scene}")

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

        summary = str(data.get("summary", ""))
        knowledge_points = list(data.get("knowledge_points", []) or [])
        sources = list(data.get("sources", []) or [])
        key_takeaways = list(data.get("key_takeaways", []) or [])
        further_reading = list(data.get("further_reading", []) or [])
        topics = list(data.get("topics", []) or [])

        metadata: dict[str, Any] = {
            "knowledge_points": knowledge_points,
            "sources": sources,
            "key_takeaways": key_takeaways,
            "further_reading": further_reading,
        }

        return AnalysisResult(
            segment_id=segment.id,
            scene=segment.scene,
            summary=summary,
            key_points=[str(x) for x in key_takeaways],
            action_items=[f"延伸阅读: {x}" for x in further_reading],
            topics=[str(x) for x in topics],
            raw_text=transcript,
            metadata=metadata,
        )


def _format_mmss(seconds: float) -> str:
    sec = max(0, int(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m:02d}:{s:02d}"

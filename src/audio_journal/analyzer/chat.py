from __future__ import annotations

from typing import Any

from audio_journal.analyzer.base import BaseAnalyzer, render_transcript
from audio_journal.llm.base import parse_json_strict
from audio_journal.models.schemas import AnalysisResult, ClassifiedSegment, SceneType


class ChatAnalyzer(BaseAnalyzer):
    """闲聊对话分析器（带价值检测）。"""

    async def analyze(self, segment: ClassifiedSegment) -> AnalysisResult:
        if segment.scene != SceneType.CHAT:
            raise ValueError(f"ChatAnalyzer 仅支持 chat，当前: {segment.scene}")

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
        all_topics = list(data.get("all_topics", []) or [])
        high_value_topics = list(data.get("high_value_topics", []) or [])
        topic_categories = list(data.get("topic_categories", []) or [])
        key_insights = list(data.get("key_insights", []) or [])
        value_score = float(data.get("value_score", 0.0))
        topics = list(data.get("topics", []) or [])

        # 价值等级判断
        if value_score >= 0.6:
            value_level = "high"
        elif value_score >= 0.3:
            value_level = "medium"
        else:
            value_level = "low"

        metadata: dict[str, Any] = {
            "all_topics": all_topics,
            "high_value_topics": high_value_topics,
            "topic_categories": topic_categories,
            "key_insights": key_insights,
            "value_score": value_score,
        }

        return AnalysisResult(
            segment_id=segment.id,
            scene=segment.scene,
            summary=summary,
            key_points=[str(x) for x in key_insights],
            topics=[str(x) for x in topics],
            value_level=value_level,
            raw_text=transcript,
            metadata=metadata,
        )


def _format_mmss(seconds: float) -> str:
    sec = max(0, int(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m:02d}:{s:02d}"

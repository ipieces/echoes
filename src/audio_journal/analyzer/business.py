from __future__ import annotations

from typing import Any

from audio_journal.analyzer.base import BaseAnalyzer, render_transcript
from audio_journal.llm.base import parse_json_strict
from audio_journal.models.schemas import AnalysisResult, ClassifiedSegment, SceneType


class BusinessAnalyzer(BaseAnalyzer):
    """商务对话分析器。"""

    async def analyze(self, segment: ClassifiedSegment) -> AnalysisResult:
        if segment.scene != SceneType.BUSINESS:
            raise ValueError(f"BusinessAnalyzer 仅支持 business，当前: {segment.scene}")

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
        commitments = list(data.get("commitments", []) or [])
        follow_ups = list(data.get("follow_ups", []) or [])
        key_asks = list(data.get("key_asks", []) or [])
        opportunities = list(data.get("opportunities", []) or [])
        participants = list(data.get("participants", []) or [])
        topics = list(data.get("topics", []) or [])

        metadata: dict[str, Any] = {
            "commitments": commitments,
            "follow_ups": follow_ups,
            "key_asks": key_asks,
            "opportunities": opportunities,
            "participants": participants,
            "topics": topics,
        }

        return AnalysisResult(
            segment_id=segment.id,
            scene=segment.scene,
            summary=summary,
            key_points=commitments,  # 承诺作为关键要点
            action_items=[str(x) for x in follow_ups],  # 后续跟进作为待办
            participants=[str(x) for x in participants],
            topics=[str(x) for x in topics],
            raw_text=transcript,
            metadata=metadata,
        )


def _format_mmss(seconds: float) -> str:
    sec = max(0, int(seconds))
    m = sec // 60
    s = sec % 60
    return f"{m:02d}:{s:02d}"

from __future__ import annotations

from typing import Any

from audio_journal.analyzer.base import BaseAnalyzer, render_transcript
from audio_journal.llm.base import parse_json_strict
from audio_journal.models.schemas import AnalysisResult, ClassifiedSegment, MergedSegment, SceneType


class PhoneAnalyzer(BaseAnalyzer):
    """电话通话分析器。"""

    async def analyze(self, segment: ClassifiedSegment | MergedSegment) -> AnalysisResult:
        if segment.scene != SceneType.PHONE:
            raise ValueError(f"PhoneAnalyzer 仅支持 phone，当前: {segment.scene}")

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
        caller_intent = str(data.get("caller_intent", ""))
        agreed_actions = list(data.get("agreed_actions", []) or [])
        follow_up = str(data.get("follow_up", ""))
        participants = list(data.get("participants", []) or [])
        topics = list(data.get("topics", []) or [])

        metadata: dict[str, Any] = {
            "caller_intent": caller_intent,
            "agreed_actions": agreed_actions,
            "follow_up": follow_up,
            "participants": participants,
        }

        action_items = [str(x) for x in agreed_actions]
        if follow_up:
            action_items.append(f"跟进: {follow_up}")

        return AnalysisResult(
            segment_id=segment.id,
            scene=segment.scene,
            summary=summary,
            key_points=[f"来电意图: {caller_intent}"] if caller_intent else [],
            action_items=action_items,
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

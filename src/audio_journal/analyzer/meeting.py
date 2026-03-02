from __future__ import annotations

from typing import Any

from audio_journal.analyzer.base import BaseAnalyzer, render_transcript
from audio_journal.llm.base import parse_json_strict
from audio_journal.models.schemas import (
    AnalysisResult,
    ClassifiedSegment,
    MergedSegment,
    SceneType,
)


class MeetingAnalyzer(BaseAnalyzer):
    """工作会议分析器。"""

    async def analyze(self, segment: ClassifiedSegment | MergedSegment) -> AnalysisResult:
        if segment.scene != SceneType.MEETING:
            raise ValueError(f"MeetingAnalyzer 仅支持 meeting，当前: {segment.scene}")

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
        key_points = list(data.get("key_points", []) or [])
        decisions = list(data.get("decisions", []) or [])
        participants = list(data.get("participants", []) or [])
        topics = list(data.get("topics", []) or [])
        action_items_raw = list(data.get("action_items", []) or [])

        action_items_display: list[str] = []
        for item in action_items_raw:
            if isinstance(item, dict):
                task = str(item.get("task", ""))
                owner = str(item.get("owner", ""))
                deadline = item.get("deadline", None)
                if deadline is None or str(deadline).lower() == "null":
                    deadline_str = ""
                else:
                    deadline_str = str(deadline)

                parts = [task]
                if owner:
                    parts.append(f"[{owner}]")
                if deadline_str:
                    parts.append(f"({deadline_str})")
                action_items_display.append(" ".join(p for p in parts if p).strip())
            else:
                action_items_display.append(str(item))

        metadata: dict[str, Any] = {
            "decisions": decisions,
            "participants": participants,
            "topics": topics,
            "action_items": action_items_raw,
        }

        return AnalysisResult(
            segment_id=segment.id,
            scene=segment.scene,
            summary=summary,
            key_points=[str(x) for x in key_points],
            action_items=action_items_display,
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

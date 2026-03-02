from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SceneType(str, Enum):
    """片段所属的场景类型。"""

    MEETING = "meeting"
    BUSINESS = "business"
    IDEA = "idea"
    LEARNING = "learning"
    PHONE = "phone"
    CHAT = "chat"


class Speaker(BaseModel):
    id: str
    label: Optional[str] = None


class Utterance(BaseModel):
    """ASR 转写得到的单条发言。"""

    speaker: Speaker
    text: str
    start_time: float
    end_time: float


class Segment(BaseModel):
    """分段后的一个片段。"""

    id: str
    utterances: list[Utterance]
    start_time: float
    end_time: float
    duration: float
    source_file: str


class ClassifiedSegment(Segment):
    """分类后的片段。"""

    scene: SceneType
    confidence: float
    value_tags: list[str] = Field(default_factory=list)


class MergedSegment(BaseModel):
    """合并后的 Segment，保留原始 Segment 信息以便追溯。"""

    id: str
    scene: SceneType
    utterances: list[Utterance]
    start_time: float
    end_time: float
    duration: float
    source_file: str
    confidence: float
    value_tags: list[str] = Field(default_factory=list)

    # 合并元数据
    original_segment_ids: list[str]
    gap_durations: list[float]


class ActionItem(BaseModel):
    task: str
    owner: str
    deadline: Optional[str] = None


class AnalysisResult(BaseModel):
    """分析结果（MVP 允许部分字段为空）。"""

    segment_id: str
    scene: SceneType
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    value_level: str = "normal"
    raw_text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewDecision(str, Enum):
    ACCEPT = "accept"
    EDIT = "edit"
    SKIP = "skip"
    DISCARD = "discard"


class ArchiveTarget(str, Enum):
    LOCAL = "local"
    OBSIDIAN = "obsidian"


class DailyReport(BaseModel):
    """日级批处理报告。"""

    date: str  # YYYY-MM-DD
    file_count: int
    results: list[AnalysisResult]
    source_files: list[str]

    @property
    def segment_count(self) -> int:
        return len(self.results)

    @property
    def scene_distribution(self) -> dict[str, int]:
        from collections import Counter

        return dict(Counter(r.scene.value for r in self.results))

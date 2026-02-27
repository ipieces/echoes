from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Iterable, Optional

import yaml

from audio_journal.models.schemas import AnalysisResult
from audio_journal.storage.index import ArchiveEntry, JSONLArchiveIndex


class LocalArchiver:
    """本地 Markdown 归档器（Phase 1 MVP）。"""

    def __init__(self, *, base_dir: str | Path, index: Optional[JSONLArchiveIndex] = None) -> None:
        self.base_dir = Path(base_dir)
        self.index = index or JSONLArchiveIndex(self.base_dir)

    def archive(
        self,
        result: AnalysisResult,
        *,
        archive_date: str | None = None,
        source_file: str = "",
        title: str | None = None,
        duration: float | None = None,
    ) -> ArchiveEntry:
        d = archive_date or date.today().isoformat()
        seq = self.index.next_sequence(d)
        entry_id = d.replace("-", "") + f"-{seq:03d}"

        final_title = title or self._suggest_title(result)
        slug = _slugify(final_title) or "entry"

        fname = f"{seq:03d}-{result.scene.value}-{slug}.md"
        day_dir = self.base_dir / d
        day_dir.mkdir(parents=True, exist_ok=True)
        md_path = (day_dir / fname).resolve()

        md_path.write_text(
            _render_markdown(
                entry_id=entry_id,
                archive_date=d,
                scene=result.scene.value,
                title=final_title,
                duration=duration if duration is not None else 0.0,
                source_file=source_file,
                segment_id=result.segment_id,
                summary=result.summary,
                key_points=result.key_points,
                action_items=result.action_items,
                topics=result.topics,
                raw_text=result.raw_text,
            ),
            encoding="utf-8",
        )

        entry = ArchiveEntry(
            id=entry_id,
            date=d,
            scene=result.scene,
            title=final_title,
            duration=float(duration or 0.0),
            archive_path=str(md_path),
            source_file=source_file,
            segment_id=result.segment_id,
        )
        self.index.append(entry)
        return entry

    def archive_all(
        self,
        results: Iterable[AnalysisResult],
        *,
        archive_date: str | None = None,
        source_file: str = "",
    ) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        for r in results:
            entries.append(self.archive(r, archive_date=archive_date, source_file=source_file))
        return entries

    @staticmethod
    def _suggest_title(result: AnalysisResult) -> str:
        if result.topics:
            return str(result.topics[0])
        if result.key_points:
            return str(result.key_points[0])
        if result.summary:
            return str(result.summary)[:20]
        return result.scene.value


# 保留中文等 Unicode 字符，避免标题被清空。
_slug_re = re.compile(r"[^\w-]+", re.UNICODE)


def _slugify(title: str) -> str:
    s = title.strip().replace(" ", "-")
    s = _slug_re.sub("-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s.lower()


def _render_markdown(
    *,
    entry_id: str,
    archive_date: str,
    scene: str,
    title: str,
    duration: float,
    source_file: str,
    segment_id: str,
    summary: str,
    key_points: list[str],
    action_items: list[str],
    topics: list[str],
    raw_text: str,
) -> str:
    front: dict[str, object] = {
        "id": entry_id,
        "date": archive_date,
        "scene": scene,
        "duration": float(duration),
        "source_file": source_file,
        "segment_id": segment_id,
    }
    if topics:
        front["topics"] = topics

    # 用 YAML dump 生成 front-matter，避免 title/topics 中的特殊字符破坏格式。
    front_yaml = yaml.dump(front, allow_unicode=True, sort_keys=False).strip()

    lines = ["---", front_yaml, "---", "", f"# {title}"]
    lines.append("")
    lines.append("## 摘要")
    lines.append(summary or "")
    lines.append("")

    lines.append("## 关键要点")
    if key_points:
        for kp in key_points:
            lines.append(f"- {kp}")
    lines.append("")

    lines.append("## 待办事项")
    if action_items:
        for ai in action_items:
            lines.append(f"- {ai}")
    lines.append("")

    lines.append("## 原始转写")
    lines.append("```text")
    lines.append(raw_text)
    lines.append("```")
    lines.append("")

    return "\n".join(lines)

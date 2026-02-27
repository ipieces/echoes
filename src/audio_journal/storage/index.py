from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

from pydantic import BaseModel

from audio_journal.models.schemas import SceneType


class ArchiveEntry(BaseModel):
    id: str
    date: str  # YYYY-MM-DD
    scene: SceneType
    title: str
    duration: float
    archive_path: str
    source_file: str
    segment_id: str


class JSONLArchiveIndex:
    """基于 JSONL 的归档索引（每天一个文件）。"""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def index_path(self, date: str) -> Path:
        return self.base_dir / date / "index.jsonl"

    def append(self, entry: ArchiveEntry) -> None:
        path = self.index_path(entry.date)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry.model_dump(mode="json"), ensure_ascii=False) + "\n")

    def list(
        self, *, date: Optional[str] = None, scene: Optional[SceneType] = None
    ) -> list[ArchiveEntry]:
        entries: list[ArchiveEntry] = []
        if date is not None:
            entries.extend(self._read_index(self.index_path(date)))
        else:
            for p in sorted(self.base_dir.glob("*/index.jsonl")):
                entries.extend(self._read_index(p))

        if scene is not None:
            entries = [e for e in entries if e.scene == scene]

        # id 默认包含日期前缀，按 id 排序可得到较稳定顺序。
        return sorted(entries, key=lambda e: e.id)

    def get_by_id(self, entry_id: str) -> ArchiveEntry | None:
        # 优先通过日期前缀定位：YYYYMMDD-xxx
        if len(entry_id) >= 8 and entry_id[0:8].isdigit():
            date = f"{entry_id[0:4]}-{entry_id[4:6]}-{entry_id[6:8]}"
            for e in self._read_index(self.index_path(date)):
                if e.id == entry_id:
                    return e
            return None

        for e in self.list():
            if e.id == entry_id:
                return e
        return None

    def next_sequence(self, date: str) -> int:
        existing = self._read_index(self.index_path(date))
        max_seq = 0
        for e in existing:
            # id: YYYYMMDD-001
            if "-" in e.id:
                try:
                    seq = int(e.id.split("-", 1)[1])
                    max_seq = max(max_seq, seq)
                except ValueError:
                    continue
        return max_seq + 1

    @staticmethod
    def _read_index(path: Path) -> list[ArchiveEntry]:
        if not path.exists():
            return []
        out: list[ArchiveEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            out.append(ArchiveEntry.model_validate_json(line))
        return out

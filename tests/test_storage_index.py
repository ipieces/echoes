from __future__ import annotations

from pathlib import Path

from audio_journal.models.schemas import SceneType
from audio_journal.storage.index import ArchiveEntry, JSONLArchiveIndex


def test_index_append_and_query_by_date(tmp_path: Path) -> None:
    idx = JSONLArchiveIndex(tmp_path)

    e1 = ArchiveEntry(
        id="20260227-001",
        date="2026-02-27",
        scene=SceneType.MEETING,
        title="t1",
        duration=1.0,
        archive_path=str(tmp_path / "x.md"),
        source_file="a.wav",
        segment_id="seg-1",
    )
    e2 = ArchiveEntry(
        id="20260228-001",
        date="2026-02-28",
        scene=SceneType.PHONE,
        title="t2",
        duration=1.0,
        archive_path=str(tmp_path / "y.md"),
        source_file="b.wav",
        segment_id="seg-2",
    )

    idx.append(e1)
    idx.append(e2)

    d1 = idx.list(date="2026-02-27")
    assert [x.id for x in d1] == ["20260227-001"]


def test_index_query_by_scene(tmp_path: Path) -> None:
    idx = JSONLArchiveIndex(tmp_path)

    idx.append(
        ArchiveEntry(
            id="20260227-001",
            date="2026-02-27",
            scene=SceneType.MEETING,
            title="t1",
            duration=1.0,
            archive_path=str(tmp_path / "x.md"),
            source_file="a.wav",
            segment_id="seg-1",
        )
    )
    idx.append(
        ArchiveEntry(
            id="20260227-002",
            date="2026-02-27",
            scene=SceneType.PHONE,
            title="t2",
            duration=1.0,
            archive_path=str(tmp_path / "y.md"),
            source_file="a.wav",
            segment_id="seg-2",
        )
    )

    meeting = idx.list(scene=SceneType.MEETING)
    assert [x.id for x in meeting] == ["20260227-001"]


def test_index_get_by_id(tmp_path: Path) -> None:
    idx = JSONLArchiveIndex(tmp_path)
    e1 = ArchiveEntry(
        id="20260227-001",
        date="2026-02-27",
        scene=SceneType.MEETING,
        title="t1",
        duration=1.0,
        archive_path=str(tmp_path / "x.md"),
        source_file="a.wav",
        segment_id="seg-1",
    )
    idx.append(e1)

    found = idx.get_by_id("20260227-001")
    assert found is not None
    assert found.title == "t1"

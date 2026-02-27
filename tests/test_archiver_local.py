from __future__ import annotations

from pathlib import Path

from audio_journal.archiver.local import LocalArchiver
from audio_journal.models.schemas import AnalysisResult, SceneType
from audio_journal.storage.index import JSONLArchiveIndex


def test_archiver_writes_markdown_and_updates_index(tmp_path: Path) -> None:
    idx = JSONLArchiveIndex(tmp_path)
    archiver = LocalArchiver(base_dir=tmp_path, index=idx)

    r = AnalysisResult(
        segment_id="seg-1",
        scene=SceneType.MEETING,
        summary="s",
        key_points=["k1"],
        action_items=["a1"],
        topics=["t"],
        raw_text="[00:00:00] SPEAKER_00: hi",
    )

    entry = archiver.archive(
        r,
        archive_date="2026-02-27",
        source_file="a.wav",
        title="Hello world",
        duration=12.3,
    )

    assert Path(entry.archive_path).exists()
    index_path = tmp_path / "2026-02-27" / "index.jsonl"
    assert index_path.exists()
    assert index_path.read_text(encoding="utf-8").strip()


def test_archiver_sanitizes_title_for_filename(tmp_path: Path) -> None:
    archiver = LocalArchiver(base_dir=tmp_path)

    r = AnalysisResult(
        segment_id="seg-1",
        scene=SceneType.MEETING,
        summary="s",
        raw_text="x",
    )

    entry = archiver.archive(
        r,
        archive_date="2026-02-27",
        title="Hello, world!! 2026",
    )

    p = Path(entry.archive_path)
    assert "hello-world-2026" in p.name


def test_archiver_slugify_keeps_chinese_title(tmp_path: Path) -> None:
    archiver = LocalArchiver(base_dir=tmp_path)

    r = AnalysisResult(
        segment_id="seg-1",
        scene=SceneType.MEETING,
        summary="s",
        raw_text="x",
    )

    entry = archiver.archive(
        r,
        archive_date="2026-02-27",
        title="中文标题：测试",
    )

    p = Path(entry.archive_path)
    assert "中文标题-测试" in p.name

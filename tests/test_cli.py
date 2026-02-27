from __future__ import annotations

import datetime
from pathlib import Path

from click.testing import CliRunner

import audio_journal.cli as cli
from audio_journal.models.schemas import SceneType
from audio_journal.storage.index import ArchiveEntry, JSONLArchiveIndex


def _write_config(tmp_path: Path, archive_dir: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        f"""
archive:
  default_target: local
  local:
    base_dir: {archive_dir.as_posix()}
paths:
  processing: {tmp_path.as_posix()}/processing
  prompts: {tmp_path.as_posix()}/prompts
watcher:
  watch_dir: {tmp_path.as_posix()}/inbox
""".lstrip(),
        encoding="utf-8",
    )
    return cfg


def test_cli_list_filters(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    cfg = _write_config(tmp_path, archive_dir)

    idx = JSONLArchiveIndex(archive_dir)
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

    runner = CliRunner()
    res = runner.invoke(cli.main, ["--config", str(cfg), "list", "--scene", "meeting"])
    assert res.exit_code == 0
    assert "20260227-001" in res.output


def test_cli_show(tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    cfg = _write_config(tmp_path, archive_dir)

    md = tmp_path / "x.md"
    md.write_text("## 摘要\nhello\n", encoding="utf-8")

    idx = JSONLArchiveIndex(archive_dir)
    idx.append(
        ArchiveEntry(
            id="20260227-001",
            date="2026-02-27",
            scene=SceneType.MEETING,
            title="t1",
            duration=1.0,
            archive_path=str(md),
            source_file="a.wav",
            segment_id="seg-1",
        )
    )

    runner = CliRunner()
    res = runner.invoke(cli.main, ["--config", str(cfg), "show", "20260227-001"])
    assert res.exit_code == 0
    assert "hello" in res.output


def test_cli_process_uses_pipeline(monkeypatch, tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    cfg = _write_config(tmp_path, archive_dir)

    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")

    class _FakePipeline:
        def __init__(self) -> None:
            self.called = False

        async def process(self, audio_path: Path):
            self.called = True
            return []

    fake = _FakePipeline()

    monkeypatch.setattr(cli, "create_pipeline", lambda config: fake)

    runner = CliRunner()
    res = runner.invoke(cli.main, ["--config", str(cfg), "process", str(wav)])
    assert res.exit_code == 0
    assert fake.called is True


def test_cli_status_shows_today_archive_count(monkeypatch, tmp_path: Path) -> None:
    archive_dir = tmp_path / "archive"
    cfg = _write_config(tmp_path, archive_dir)

    class _FakeDate:
        @classmethod
        def today(cls):
            return datetime.date(2026, 2, 27)

    monkeypatch.setattr(cli, "date", _FakeDate)

    idx = JSONLArchiveIndex(archive_dir)
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
            source_file="b.wav",
            segment_id="seg-2",
        )
    )

    runner = CliRunner()
    res = runner.invoke(cli.main, ["--config", str(cfg), "status"])
    assert res.exit_code == 0
    assert "今日归档: 2 条" in res.output
    assert "meeting(1)" in res.output
    assert "phone(1)" in res.output

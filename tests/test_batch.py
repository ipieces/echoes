"""测试日级批处理功能。"""

from __future__ import annotations

import asyncio
import wave
from datetime import date
from pathlib import Path

import pytest

from audio_journal.batch import (
    DailyBatchProcessor,
    collect_files_by_date,
    merge_wav_files,
    parse_recording_time,
)
from audio_journal.config import AppConfig, load_config
from audio_journal.models.schemas import AnalysisResult, SceneType


def test_parse_recording_time_valid() -> None:
    """测试解析有效的文件名。"""
    ts = parse_recording_time("20260301120546.WAV")
    assert ts is not None
    assert ts.year == 2026
    assert ts.month == 3
    assert ts.day == 1
    assert ts.hour == 12
    assert ts.minute == 5
    assert ts.second == 46


def test_parse_recording_time_lowercase() -> None:
    """测试小写扩展名。"""
    ts = parse_recording_time("20260301120546.wav")
    assert ts is not None
    assert ts.year == 2026


def test_parse_recording_time_invalid() -> None:
    """测试无效文件名返回 None。"""
    assert parse_recording_time("invalid.wav") is None
    assert parse_recording_time("2026030112.wav") is None
    assert parse_recording_time("20260301120546.mp3") is None


def test_parse_recording_time_invalid_date() -> None:
    """测试无效日期返回 None。"""
    assert parse_recording_time("20261301120546.wav") is None  # 13月
    assert parse_recording_time("20260230120546.wav") is None  # 2月30日


def test_collect_files_by_date_empty(tmp_path: Path) -> None:
    """测试空目录。"""
    groups = collect_files_by_date(tmp_path)
    assert groups == {}


def test_collect_files_by_date_single_day(tmp_path: Path) -> None:
    """测试单日多个文件。"""
    (tmp_path / "20260301120546.wav").write_bytes(b"x")
    (tmp_path / "20260301132609.wav").write_bytes(b"y")
    (tmp_path / "20260301154823.wav").write_bytes(b"z")

    groups = collect_files_by_date(tmp_path)
    assert len(groups) == 1
    assert date(2026, 3, 1) in groups
    files = groups[date(2026, 3, 1)]
    assert len(files) == 3
    # 验证按时间排序
    assert files[0].name == "20260301120546.wav"
    assert files[1].name == "20260301132609.wav"
    assert files[2].name == "20260301154823.wav"


def test_collect_files_by_date_multiple_days(tmp_path: Path) -> None:
    """测试多日文件。"""
    (tmp_path / "20260301120546.wav").write_bytes(b"x")
    (tmp_path / "20260302132609.wav").write_bytes(b"y")
    (tmp_path / "20260303154823.wav").write_bytes(b"z")

    groups = collect_files_by_date(tmp_path)
    assert len(groups) == 3
    assert date(2026, 3, 1) in groups
    assert date(2026, 3, 2) in groups
    assert date(2026, 3, 3) in groups


def test_collect_files_by_date_ignores_invalid(tmp_path: Path) -> None:
    """测试忽略无效文件名。"""
    (tmp_path / "20260301120546.wav").write_bytes(b"x")
    (tmp_path / "invalid.wav").write_bytes(b"y")
    (tmp_path / "readme.txt").write_bytes(b"z")

    groups = collect_files_by_date(tmp_path)
    assert len(groups) == 1
    assert len(groups[date(2026, 3, 1)]) == 1


def _create_wav(path: Path, duration_sec: float = 1.0, sample_rate: int = 16000) -> None:
    """创建一个简单的 WAV 文件。"""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * int(sample_rate * duration_sec))


def test_merge_wav_files_single(tmp_path: Path) -> None:
    """测试合并单个文件。"""
    f1 = tmp_path / "1.wav"
    _create_wav(f1, 1.0)

    out = tmp_path / "merged.wav"
    merge_wav_files([f1], out)

    assert out.exists()
    with wave.open(str(out), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 16000


def test_merge_wav_files_multiple(tmp_path: Path) -> None:
    """测试合并多个文件。"""
    f1 = tmp_path / "1.wav"
    f2 = tmp_path / "2.wav"
    f3 = tmp_path / "3.wav"
    _create_wav(f1, 1.0)
    _create_wav(f2, 1.0)
    _create_wav(f3, 1.0)

    out = tmp_path / "merged.wav"
    merge_wav_files([f1, f2, f3], out)

    assert out.exists()
    with wave.open(str(out), "rb") as w:
        # 3秒音频，16000 Hz
        assert w.getnframes() == 16000 * 3


def test_merge_wav_files_inconsistent_params(tmp_path: Path) -> None:
    """测试参数不一致时抛出异常。"""
    f1 = tmp_path / "1.wav"
    f2 = tmp_path / "2.wav"
    _create_wav(f1, 1.0, sample_rate=16000)
    _create_wav(f2, 1.0, sample_rate=8000)  # 不同采样率

    out = tmp_path / "merged.wav"
    with pytest.raises(ValueError, match="音频参数不一致"):
        merge_wav_files([f1, f2], out)


def test_merge_wav_files_empty_list(tmp_path: Path) -> None:
    """测试空列表抛出异常。"""
    out = tmp_path / "merged.wav"
    with pytest.raises(ValueError, match="没有文件可合并"):
        merge_wav_files([], out)


class _FakePipeline:
    """假的 Pipeline，返回固定结果。"""

    def __init__(self) -> None:
        self.processed_files: list[Path] = []

    async def process(self, audio_path: str | Path) -> list[AnalysisResult]:
        self.processed_files.append(Path(audio_path))
        return [
            AnalysisResult(
                segment_id="seg-1",
                scene=SceneType.MEETING,
                summary="会议",
                raw_text="测试",
            ),
            AnalysisResult(
                segment_id="seg-2",
                scene=SceneType.PHONE,
                summary="电话",
                raw_text="测试",
            ),
        ]


def test_daily_batch_processor_process_date(tmp_path: Path) -> None:
    """测试处理单个日期。"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"""
paths:
  inbox: {tmp_path.as_posix()}/inbox
  processing: {tmp_path.as_posix()}/processing
  prompts: {tmp_path.as_posix()}/prompts
archive:
  local:
    base_dir: {tmp_path.as_posix()}/archive
batch:
  processed_dir: {tmp_path.as_posix()}/processed
""".lstrip(),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    f1 = inbox / "20260301120546.wav"
    f2 = inbox / "20260301132609.wav"
    _create_wav(f1, 1.0)
    _create_wav(f2, 1.0)

    fake_pipe = _FakePipeline()
    processor = DailyBatchProcessor(cfg, pipeline=fake_pipe)

    report = asyncio.run(processor.process_date(date(2026, 3, 1)))

    assert report.date == "2026-03-01"
    assert report.file_count == 2
    assert report.segment_count == 2
    assert report.scene_distribution == {"meeting": 1, "phone": 1}
    assert len(report.source_files) == 2

    # 验证原始文件已移动
    assert not f1.exists()
    assert not f2.exists()
    processed_dir = tmp_path / "processed" / "2026-03-01"
    assert (processed_dir / "20260301120546.wav").exists()
    assert (processed_dir / "20260301132609.wav").exists()

    # 验证临时合并文件已删除
    merged = tmp_path / "processing" / "2026-03-01-merged.wav"
    assert not merged.exists()


def test_daily_batch_processor_process_date_empty(tmp_path: Path) -> None:
    """测试处理空日期。"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"""
paths:
  inbox: {tmp_path.as_posix()}/inbox
  processing: {tmp_path.as_posix()}/processing
  prompts: {tmp_path.as_posix()}/prompts
archive:
  local:
    base_dir: {tmp_path.as_posix()}/archive
batch:
  processed_dir: {tmp_path.as_posix()}/processed
""".lstrip(),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)

    inbox = tmp_path / "inbox"
    inbox.mkdir()

    fake_pipe = _FakePipeline()
    processor = DailyBatchProcessor(cfg, pipeline=fake_pipe)

    report = asyncio.run(processor.process_date(date(2026, 3, 1)))

    assert report.date == "2026-03-01"
    assert report.file_count == 0
    assert report.segment_count == 0
    assert report.scene_distribution == {}


def test_daily_batch_processor_process_all(tmp_path: Path) -> None:
    """测试处理所有日期。"""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        f"""
paths:
  inbox: {tmp_path.as_posix()}/inbox
  processing: {tmp_path.as_posix()}/processing
  prompts: {tmp_path.as_posix()}/prompts
archive:
  local:
    base_dir: {tmp_path.as_posix()}/archive
batch:
  processed_dir: {tmp_path.as_posix()}/processed
""".lstrip(),
        encoding="utf-8",
    )
    cfg = load_config(cfg_path)

    inbox = tmp_path / "inbox"
    inbox.mkdir()
    _create_wav(inbox / "20260301120546.wav", 1.0)
    _create_wav(inbox / "20260302132609.wav", 1.0)
    _create_wav(inbox / "20260303154823.wav", 1.0)

    fake_pipe = _FakePipeline()
    processor = DailyBatchProcessor(cfg, pipeline=fake_pipe)

    reports = asyncio.run(processor.process_all())

    assert len(reports) == 3
    assert reports[0].date == "2026-03-01"
    assert reports[1].date == "2026-03-02"
    assert reports[2].date == "2026-03-03"
    assert all(r.file_count == 1 for r in reports)

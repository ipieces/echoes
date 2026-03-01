"""日级批处理：收集当天 WAV → 合并 → 走现有 Pipeline → 清理归档。"""

from __future__ import annotations

import re
import shutil
import tempfile
import wave
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from audio_journal.config import AppConfig
from audio_journal.models.schemas import AnalysisResult, DailyReport
from audio_journal.pipeline import Pipeline

# 匹配 YYYYMMDDHHMMSS.WAV
_FILENAME_RE = re.compile(
    r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\.wav$", re.IGNORECASE
)


def parse_recording_time(filename: str) -> datetime | None:
    """从文件名解析录音时间戳，无法解析返回 None。"""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None
    try:
        return datetime(
            int(m.group(1)), int(m.group(2)), int(m.group(3)),
            int(m.group(4)), int(m.group(5)), int(m.group(6)),
        )
    except ValueError:
        return None


def collect_files_by_date(
    inbox: Path,
) -> dict[date, list[Path]]:
    """扫描 inbox 目录，按日期分组并按时间排序。"""
    groups: dict[date, list[tuple[datetime, Path]]] = defaultdict(list)
    for f in inbox.iterdir():
        if not f.is_file():
            continue
        ts = parse_recording_time(f.name)
        if ts is None:
            continue
        groups[ts.date()].append((ts, f))

    result: dict[date, list[Path]] = {}
    for d, items in sorted(groups.items()):
        items.sort(key=lambda x: x[0])
        result[d] = [p for _, p in items]
    return result


def merge_wav_files(files: list[Path], output: Path) -> Path:
    """将多个 WAV 文件拼接为一个，参数不一致时抛出 ValueError。"""
    if not files:
        raise ValueError("没有文件可合并")

    # 读取第一个文件的参数作为基准
    with wave.open(str(files[0]), "rb") as first:
        params = first.getparams()

    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as out:
        out.setparams(params)
        for f in files:
            with wave.open(str(f), "rb") as inp:
                inp_params = inp.getparams()
                if (
                    inp_params.nchannels != params.nchannels
                    or inp_params.sampwidth != params.sampwidth
                    or inp_params.framerate != params.framerate
                ):
                    raise ValueError(
                        f"音频参数不一致: {f.name} "
                        f"(channels={inp_params.nchannels}, "
                        f"sampwidth={inp_params.sampwidth}, "
                        f"framerate={inp_params.framerate}) "
                        f"vs 基准 "
                        f"(channels={params.nchannels}, "
                        f"sampwidth={params.sampwidth}, "
                        f"framerate={params.framerate})"
                    )
                out.writeframes(inp.readframes(inp.getnframes()))
    return output


class DailyBatchProcessor:
    """日级批处理器：合并 → Pipeline → 清理。"""

    def __init__(self, config: AppConfig, pipeline: Pipeline | None = None) -> None:
        self.config = config
        self.pipeline = pipeline or Pipeline(config)

    async def process_date(self, target_date: date) -> DailyReport:
        """处理指定日期的所有录音文件。"""
        inbox = self.config.paths.inbox
        all_groups = collect_files_by_date(inbox)
        files = all_groups.get(target_date, [])

        if not files:
            return DailyReport(
                date=target_date.isoformat(),
                file_count=0,
                results=[],
                source_files=[],
            )

        # 合并到临时文件
        processing_dir = self.config.paths.processing
        processing_dir.mkdir(parents=True, exist_ok=True)
        merged_path = processing_dir / f"{target_date.isoformat()}-merged.wav"

        try:
            merge_wav_files(files, merged_path)

            # 走现有 Pipeline
            results = await self.pipeline.process(merged_path)

            # 移动原始文件到 processed/YYYY-MM-DD/
            processed_dir = self.config.batch.processed_dir / target_date.isoformat()
            processed_dir.mkdir(parents=True, exist_ok=True)
            for f in files:
                shutil.move(str(f), str(processed_dir / f.name))

            return DailyReport(
                date=target_date.isoformat(),
                file_count=len(files),
                results=results,
                source_files=[f.name for f in files],
            )
        finally:
            # 无论成功失败，清理临时合并文件
            if merged_path.exists():
                merged_path.unlink()

    async def process_all(self) -> list[DailyReport]:
        """处理 inbox 中所有日期。"""
        inbox = self.config.paths.inbox
        all_groups = collect_files_by_date(inbox)
        reports: list[DailyReport] = []
        for d in sorted(all_groups.keys()):
            report = await self.process_date(d)
            reports.append(report)
        return reports

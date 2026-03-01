from __future__ import annotations

import asyncio
from collections import Counter
from datetime import date
from pathlib import Path

import click

from audio_journal.batch import DailyBatchProcessor, collect_files_by_date
from audio_journal.config import AppConfig, load_config
from audio_journal.models.schemas import SceneType
from audio_journal.pipeline import Pipeline
from audio_journal.storage.index import JSONLArchiveIndex
from audio_journal.watcher.file_watcher import FileWatcher


def create_pipeline(config: AppConfig) -> Pipeline:
    return Pipeline(config)


@click.group()
@click.option(
    "--config",
    "config_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("./config.yaml"),
    show_default=True,
)
@click.pass_context
def main(ctx: click.Context, config_path: Path) -> None:
    """Audio Journal CLI（Phase 1 MVP）。"""

    if not config_path.exists():
        raise click.FileError(str(config_path), hint="配置文件不存在")

    ctx.obj = {
        "config": load_config(config_path),
    }


@main.command()
@click.argument("wav_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.pass_obj
def process(obj: dict, wav_path: Path) -> None:
    """手动处理单个 WAV 文件。"""

    cfg: AppConfig = obj["config"]
    pipe = create_pipeline(cfg)
    results = asyncio.run(pipe.process(wav_path))
    click.echo(f"\u2705 已归档 {len(results)} 条")


@main.command()
@click.pass_obj
def start(obj: dict) -> None:
    """前台启动监听服务。"""

    cfg: AppConfig = obj["config"]
    pipe = create_pipeline(cfg)

    watcher = FileWatcher(
        watch_dir=cfg.watcher.watch_dir,
        patterns=cfg.watcher.patterns,
        stable_seconds=cfg.watcher.stable_seconds,
    )

    def _on_audio_ready(p: Path) -> None:
        # 已知限制：这里在 watchdog 的回调线程里直接 asyncio.run，会为每个文件创建新 event loop。
        # 如果单次处理耗时较长且新文件持续进入，回调线程会被阻塞（MVP 阶段先接受，后续应改为队列+后台 worker）。
        asyncio.run(pipe.process(p))

    click.echo("\U0001F399\ufe0f Audio Journal 服务启动")
    click.echo(f"  监听目录: {cfg.watcher.watch_dir}")
    click.echo("  等待新录音文件...\n")
    watcher.start(_on_audio_ready)


@main.command()
@click.pass_obj
def status(obj: dict) -> None:
    """显示最近归档与简单统计（MVP 不做常驻服务状态）。"""

    cfg: AppConfig = obj["config"]
    idx = JSONLArchiveIndex(cfg.archive.local.base_dir)

    today = date.today().isoformat()
    entries = idx.list(date=today)

    click.echo("\U0001F4CA Audio Journal 状态\n")
    click.echo("  服务: ○ 未实现 daemon（Phase 1）")
    click.echo(f"  今日归档: {len(entries)} 条")

    dist = Counter(e.scene.value for e in entries)
    if dist:
        click.echo("  场景分布: " + " ".join(f"{k}({v})" for k, v in sorted(dist.items())))


@main.command(name="list")
@click.option("--date", "date_filter", type=str, default=None)
@click.option("--scene", "scene_filter", type=click.Choice([s.value for s in SceneType]), default=None)
@click.pass_obj
def list_entries(obj: dict, date_filter: str | None, scene_filter: str | None) -> None:
    """列出归档条目。"""

    cfg: AppConfig = obj["config"]
    idx = JSONLArchiveIndex(cfg.archive.local.base_dir)

    scene = SceneType(scene_filter) if scene_filter else None
    entries = idx.list(date=date_filter, scene=scene)

    for e in entries:
        click.echo(f"{e.id}\t{e.date}\t{e.scene.value}\t{e.title}")


@main.command()
@click.argument("entry_id", type=str)
@click.pass_obj
def show(obj: dict, entry_id: str) -> None:
    """展示单条归档详情。"""

    cfg: AppConfig = obj["config"]
    idx = JSONLArchiveIndex(cfg.archive.local.base_dir)
    entry = idx.get_by_id(entry_id)
    if entry is None:
        raise click.ClickException(f"未找到记录: {entry_id}")

    md_path = Path(entry.archive_path)
    click.echo("\n".join([
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"{entry.scene.value} | {entry.date} | {entry.id}",
        f"标题: {entry.title}",
        f"文件: {md_path}",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n",
    ]))

    if md_path.exists():
        click.echo(md_path.read_text(encoding="utf-8"))
    else:
        click.echo("(归档文件不存在)")


@main.command()
@click.option(
    "--date",
    "target_date",
    type=str,
    default=None,
    help="处理指定日期（YYYY-MM-DD），默认处理昨天",
)
@click.pass_obj
def batch(obj: dict, target_date: str | None) -> None:
    """批量处理指定日期的所有录音。"""
    from datetime import timedelta

    cfg: AppConfig = obj["config"]

    # 默认处理昨天
    if target_date is None:
        d = date.today() - timedelta(days=1)
    else:
        try:
            d = date.fromisoformat(target_date)
        except ValueError:
            raise click.BadParameter(f"日期格式错误: {target_date}，应为 YYYY-MM-DD")

    # 检查是否有文件
    all_groups = collect_files_by_date(cfg.paths.inbox)
    files = all_groups.get(d, [])

    if not files:
        click.echo(f"📭 {d.isoformat()} 没有找到录音文件")
        return

    click.echo(f"🎙️  发现 {len(files)} 个录音文件 ({d.isoformat()})")
    for f in files:
        click.echo(f"  - {f.name}")

    # 处理
    processor = DailyBatchProcessor(cfg)
    click.echo(f"\n⏳ 合并音频并处理...")
    report = asyncio.run(processor.process_date(d))

    click.echo(f"\n✅ 处理完成")
    click.echo(f"  文件数: {report.file_count}")
    click.echo(f"  片段数: {report.segment_count}")
    if report.scene_distribution:
        click.echo(f"  场景分布: {report.scene_distribution}")


@main.command(name="batch-all")
@click.pass_obj
def batch_all(obj: dict) -> None:
    """处理 inbox 中所有未处理的日期。"""
    cfg: AppConfig = obj["config"]
    all_groups = collect_files_by_date(cfg.paths.inbox)

    if not all_groups:
        click.echo("📭 inbox 为空")
        return

    click.echo(f"📅 发现 {len(all_groups)} 个日期待处理\n")

    processor = DailyBatchProcessor(cfg)
    for d in sorted(all_groups.keys()):
        files = all_groups[d]
        click.echo(f"处理 {d.isoformat()} ({len(files)} 个文件)...")
        report = asyncio.run(processor.process_date(d))
        click.echo(f"  ✅ {report.segment_count} 个片段")

    click.echo(f"\n🎉 全部完成")


if __name__ == "__main__":
    main()

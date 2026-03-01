# Audio Journal — 日级批处理改造方案

> 基于现有 Phase 1 MVP 代码，将"单文件实时处理"改为"日级批处理"模式。

## 背景

录音设备每天产生若干 WAV 文件，命名规则 `YYYYMMDDHHMMSS.WAV`（如 `20260301120546.WAV`）。当前架构逐文件独立处理，存在三个问题：

1. **说话人 ID 割裂** — 文件间 SPEAKER_00 无法关联
2. **场景断裂** — 同一会议跨两个文件会被拆成两个独立分析
3. **归档碎片化** — 缺少日级全景视图

## 核心改动

### 1. 新增 DailyBatchProcessor

**位置**: `src/audio_journal/batch.py`

**职责**: 按日期收集文件 → 按时间排序 → 顺序处理 → 跨文件场景合并 → 生成日报

```python
class DailyBatchProcessor:
    """日级批处理器。"""

    def __init__(self, config: AppConfig, pipeline: Pipeline):
        self.config = config
        self.pipeline = pipeline
        self.scene_merger = SceneMerger(config)

    async def process_day(self, date: str, files: list[Path]) -> DailyReport:
        """处理一天的所有录音文件。

        Args:
            date: YYYY-MM-DD
            files: 按时间排序的 WAV 文件列表
        """
        # 1. 逐文件走 pipeline（复用现有逻辑），收集所有 segment 结果
        all_results: list[AnalysisResult] = []
        for wav in files:
            results = await self.pipeline.process_without_archive(wav)
            all_results.extend(results)

        # 2. 跨文件场景合并
        merged = self.scene_merger.merge(all_results)

        # 3. 统一归档
        entries = self.pipeline.archiver.archive_all(
            merged, archive_date=date, source_file="daily-batch"
        )

        # 4. 生成日报
        return DailyReport(date=date, files=files, entries=entries, results=merged)
```

**关键设计**:
- `Pipeline` 新增 `process_without_archive()` 方法，只跑 chunk→ASR→segment→classify→analyze，不归档
- 归档统一由 `DailyBatchProcessor` 在合并后执行
- 每个 `AnalysisResult` 需要携带源文件信息和绝对时间戳，用于后续合并判断

### 2. 文件收集器 — 从文件名解析日期

**位置**: `src/audio_journal/batch.py`（同文件）

```python
import re
from datetime import datetime

# 匹配 YYYYMMDDHHMMSS.WAV
_FILENAME_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})\.wav$", re.IGNORECASE)

def parse_recording_time(filename: str) -> datetime | None:
    """从文件名解析录音开始时间。"""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None
    return datetime(
        int(m[1]), int(m[2]), int(m[3]),
        int(m[4]), int(m[5]), int(m[6])
    )

def collect_files_by_date(inbox: Path) -> dict[str, list[Path]]:
    """扫描 inbox，按日期分组并按时间排序。"""
    groups: dict[str, list[tuple[datetime, Path]]] = {}
    for f in inbox.glob("*.wav"):
        ts = parse_recording_time(f.name)
        if ts is None:
            continue  # 跳过不符合命名规则的文件
        date_str = ts.strftime("%Y-%m-%d")
        groups.setdefault(date_str, []).append((ts, f))

    return {
        date: [p for _, p in sorted(items)]
        for date, items in sorted(groups.items())
    }
```

### 3. Pipeline 拆分：处理 vs 归档

**改动文件**: `src/audio_journal/pipeline.py`

当前 `Pipeline.process()` 末尾直接调用 `self.archiver.archive_all()`。需要拆分：

```python
class Pipeline:
    async def process(self, audio_path: str | Path) -> list[AnalysisResult]:
        """完整流程（单文件模式，保持向后兼容）。"""
        results = await self.process_without_archive(audio_path)
        self.archiver.archive_all(results, source_file=str(Path(audio_path).name))
        return results

    async def process_without_archive(self, audio_path: str | Path) -> list[AnalysisResult]:
        """只跑分析，不归档（供批处理调用）。"""
        src = Path(audio_path)
        run_dir = (self.config.paths.processing / src.stem).resolve()
        chunks_dir = run_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        chunks = self.chunker.split(src, chunks_dir)

        all_results: list[AnalysisResult] = []
        for chunk in chunks:
            utterances = self.asr.transcribe(str(chunk.path))
            segments = self.segmenter.segment(utterances, source_file=str(src.name))

            classified = []
            for seg in segments:
                classified.append(await self.classifier.classify(seg))

            for seg in classified:
                if seg.scene == SceneType.MEETING:
                    res = await self.meeting_analyzer.analyze(seg)
                else:
                    res = await self.passthrough_analyzer.analyze(seg)
                all_results.append(res)

        return all_results
```

### 4. SceneMerger — 跨文件场景合并

**位置**: `src/audio_journal/merger.py`

**合并逻辑**:
- 相邻文件的末尾/开头如果是同一场景类型（如都是 meeting），且时间间隔 < 阈值（如 5 分钟），判定为同一场景
- 合并时拼接 utterances、合并 topics/key_points，重新生成 summary

```python
class SceneMerger:
    """跨文件场景合并器。"""

    def __init__(self, config: AppConfig):
        self.max_gap_seconds = config.batch.merge_gap_seconds  # 默认 300s

    def merge(self, results: list[AnalysisResult]) -> list[AnalysisResult]:
        """合并相邻的同场景结果。"""
        if not results:
            return []

        merged: list[AnalysisResult] = [results[0]]
        for current in results[1:]:
            prev = merged[-1]
            if self._should_merge(prev, current):
                merged[-1] = self._do_merge(prev, current)
            else:
                merged.append(current)
        return merged

    def _should_merge(self, a: AnalysisResult, b: AnalysisResult) -> bool:
        """判断两个结果是否应该合并。"""
        # 场景类型必须相同
        if a.scene != b.scene:
            return False
        # 时间间隔检查（需要 metadata 中的时间信息）
        a_end = a.metadata.get("end_time", 0)
        b_start = b.metadata.get("start_time", 0)
        if b_start - a_end > self.max_gap_seconds:
            return False
        return True

    def _do_merge(self, a: AnalysisResult, b: AnalysisResult) -> AnalysisResult:
        """合并两个分析结果。"""
        return AnalysisResult(
            segment_id=a.segment_id,  # 保留第一个的 ID
            scene=a.scene,
            summary=a.summary + "\n" + b.summary,
            key_points=a.key_points + b.key_points,
            action_items=a.action_items + b.action_items,
            participants=list(set(a.participants + b.participants)),
            topics=list(dict.fromkeys(a.topics + b.topics)),  # 去重保序
            raw_text=a.raw_text + "\n\n---\n\n" + b.raw_text,
            metadata={
                **a.metadata,
                "merged_from": a.metadata.get("merged_from", [a.segment_id]) + [b.segment_id],
                "start_time": a.metadata.get("start_time", 0),
                "end_time": b.metadata.get("end_time", 0),
            },
        )
```

### 5. AnalysisResult 扩展 — 携带时间信息

**改动文件**: `src/audio_journal/models/schemas.py`

```python
class AnalysisResult(BaseModel):
    segment_id: str
    scene: SceneType
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    topics: list[str] = Field(default_factory=list)
    value_level: str = "normal"
    raw_text: str
    source_file: str = ""                    # ← 新增：源 WAV 文件名
    recording_time: Optional[str] = None     # ← 新增：录音开始时间 ISO 格式
    metadata: dict[str, Any] = Field(default_factory=dict)
```

Pipeline 处理时需要将 `source_file` 和从文件名解析的 `recording_time` 写入每个 result，SceneMerger 据此判断时间间隔。

### 6. DailyReport — 日报模型

**位置**: `src/audio_journal/models/schemas.py`

```python
class DailyReport(BaseModel):
    """一天的处理报告。"""
    date: str                          # YYYY-MM-DD
    file_count: int                    # 处理的 WAV 文件数
    total_duration_minutes: float      # 总录音时长（分钟）
    segment_count: int                 # 分析片段数（合并后）
    scene_distribution: dict[str, int] # 场景分布 {"meeting": 3, "phone": 1}
    entries: list[str]                 # 归档条目 ID 列表
```

日报归档到 `data/archive/YYYY-MM-DD/daily-report.md`，作为当天的索引页。

### 7. 配置扩展

**改动文件**: `config.yaml` + `src/audio_journal/config.py`

```yaml
batch:
  mode: daily                    # daily | realtime（保留实时模式兼容）
  merge_gap_seconds: 300         # 场景合并的最大时间间隔（秒）
  auto_move_processed: true      # 处理完后将 WAV 移到 processed/ 目录
  processed_dir: ./data/processed
```

```python
class BatchConfig(BaseModel):
    mode: Literal["daily", "realtime"] = "daily"
    merge_gap_seconds: float = 300.0
    auto_move_processed: bool = True
    processed_dir: Path = Path("./data/processed")

class AppConfig(BaseModel):
    # ... 现有字段 ...
    batch: BatchConfig = Field(default_factory=BatchConfig)
```

### 8. CLI 改造

**改动文件**: `src/audio_journal/cli.py`

```python
@main.command()
@click.option("--date", "target_date", type=str, default=None,
              help="处理指定日期，格式 YYYY-MM-DD。默认处理昨天。")
@click.pass_obj
def batch(obj: dict, target_date: str | None) -> None:
    """批量处理指定日期的所有录音。"""
    cfg: AppConfig = obj["config"]

    if target_date is None:
        target_date = (date.today() - timedelta(days=1)).isoformat()

    files_by_date = collect_files_by_date(cfg.watcher.watch_dir)
    files = files_by_date.get(target_date, [])

    if not files:
        click.echo(f"📭 {target_date} 没有找到录音文件")
        return

    click.echo(f"🎙️ 发现 {len(files)} 个录音文件 ({target_date})")
    for f in files:
        click.echo(f"  - {f.name}")

    pipe = create_pipeline(cfg)
    processor = DailyBatchProcessor(cfg, pipe)
    report = asyncio.run(processor.process_day(target_date, files))

    click.echo(f"\n✅ 处理完成: {report.segment_count} 个片段, {report.file_count} 个文件")

@main.command(name="batch-all")
@click.pass_obj
def batch_all(obj: dict) -> None:
    """处理 inbox 中所有未处理的日期。"""
    cfg: AppConfig = obj["config"]
    files_by_date = collect_files_by_date(cfg.watcher.watch_dir)

    if not files_by_date:
        click.echo("📭 inbox 为空")
        return

    pipe = create_pipeline(cfg)
    processor = DailyBatchProcessor(cfg, pipe)

    for d, files in files_by_date.items():
        click.echo(f"\n📅 处理 {d} ({len(files)} 个文件)...")
        report = asyncio.run(processor.process_day(d, files))
        click.echo(f"  ✅ {report.segment_count} 个片段")
```

### 9. Watcher 改造 — 收集模式

**改动文件**: `src/audio_journal/watcher/file_watcher.py`

实时模式保留（`batch.mode: realtime`），但默认改为收集模式：

- Watcher 仍然监听 inbox，但不再立即触发 pipeline
- 只记录新文件到 `data/pending.jsonl`（文件名 + 发现时间）
- 实际处理由 `batch` 命令或 cron 触发

```python
class CollectorHandler(FileSystemEventHandler):
    """收集模式：只记录新文件，不处理。"""

    def __init__(self, pending_log: Path, stable_seconds: float):
        self.pending_log = pending_log
        self.stable_seconds = stable_seconds

    def on_created(self, event):
        if getattr(event, "is_directory", False):
            return
        p = Path(str(getattr(event, "src_path", "")))
        if p.suffix.lower() != ".wav":
            return
        wait_stable(p, stable_seconds=self.stable_seconds)
        # 只记录，不处理
        with self.pending_log.open("a") as f:
            f.write(json.dumps({"file": str(p), "discovered": datetime.now().isoformat()}) + "\n")
```

### 10. 已处理文件管理

处理完成后，WAV 文件移动到 `data/processed/YYYY-MM-DD/` 目录：

```
data/
├── inbox/                    # 新录音放这里
│   ├── 20260302120546.WAV
│   └── 20260302132609.WAV
├── processed/                # 处理完自动移过来
│   └── 2026-03-01/
│       ├── 20260301120546.WAV
│       └── 20260301132609.WAV
├── processing/               # 临时处理目录（chunk 等）
└── archive/                  # 归档结果
    └── 2026-03-01/
        ├── daily-report.md
        ├── 001-meeting-项目进度.md
        ├── 002-phone-客户沟通.md
        └── index.jsonl
```

这样可以：
- 通过 inbox 是否为空判断有无待处理文件
- 避免重复处理
- 保留原始录音（不删除）

---

## 不改动的部分

以下模块保持不变，直接复用：

| 模块 | 原因 |
|------|------|
| `VADChunker` | 单文件切分逻辑不变 |
| `MockASR` / ASR 接口 | 转写逻辑不变 |
| `SilenceSegmenter` | 分段逻辑不变 |
| `SceneClassifier` | 分类逻辑不变 |
| `MeetingAnalyzer` | 分析逻辑不变 |
| `LocalArchiver` | 归档逻辑不变，只是调用时机变了 |
| `JSONLArchiveIndex` | 索引结构不变 |

---

## 实现顺序

| # | 任务 | 改动范围 | 依赖 |
|---|------|---------|------|
| 1 | `AnalysisResult` 新增 `source_file` + `recording_time` 字段 | schemas.py | 无 |
| 2 | Pipeline 拆分 `process_without_archive()` | pipeline.py | #1 |
| 3 | 文件收集器 `parse_recording_time` + `collect_files_by_date` | batch.py (新) | 无 |
| 4 | `BatchConfig` 配置 | config.py, config.yaml | 无 |
| 5 | `SceneMerger` 实现 | merger.py (新) | #1 |
| 6 | `DailyBatchProcessor` + `DailyReport` | batch.py, schemas.py | #2, #3, #5 |
| 7 | CLI `batch` + `batch-all` 命令 | cli.py | #6 |
| 8 | 已处理文件移动逻辑 | batch.py | #6 |
| 9 | Watcher 收集模式 | file_watcher.py | #4 |
| 10 | 日报生成 `daily-report.md` | batch.py | #6 |
| 11 | 测试用例 | tests/ | 全部 |

**预估工作量**: 新增 ~400 行代码，改动 ~50 行现有代码。

---

## 未来扩展（不在本次范围）

- **跨文件说话人关联** — 基于声纹嵌入的 SpeakerTracker（Phase 3）
- **合并后重新分析** — 合并的 segment 重新调用 LLM 生成更完整的 summary（需要额外 API 调用）
- **cron 自动触发** — 每天凌晨自动执行 `batch --date yesterday`

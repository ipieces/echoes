# Audio Journal — 日级批处理改造方案 v2

> 基于现有 Phase 1 MVP 代码，将"单文件实时处理"改为"日级批处理"模式。
> 
> **核心思路**：音频层面合并 > 文本层面合并

## 背景

录音设备每天产生若干 WAV 文件，命名规则 `YYYYMMDDHHMMSS.WAV`（如 `20260301120546.WAV`）。当前架构逐文件独立处理，存在三个问题：

1. **说话人 ID 割裂** — 文件间 SPEAKER_00 无法关联
2. **场景断裂** — 同一会议跨两个文件会被拆成两个独立分析
3. **归档碎片化** — 缺少日级全景视图

## 方案对比

### 方案 A：文本层面合并（复杂）

逐文件处理 → 收集所有 AnalysisResult → 根据场景类型和时间间隔合并

**问题**：
- 需要 SceneMerger 模块，用启发式规则判断"两个结果是否应该合并"
- 需要在 metadata 中追踪时间信息
- 合并逻辑复杂，容易出错（如何判断 5 分钟间隔是"同一会议"还是"两个会议"？）

### 方案 B：音频层面合并（简洁）✅

合并当天所有 WAV → 走现有 Pipeline → 自然分段

**优势**：
- **分段更自然** — SilenceSegmenter 根据实际静音间隔切分，不需要猜测
- **说话人 ID 一致** — ASR 处理整天音频流，SPEAKER_00 全天都是同一人
- **实现简单** — 不需要 SceneMerger、不需要时间追踪、不需要复杂逻辑
- **完全复用现有代码** — Pipeline/Chunker/Segmenter/Classifier/Analyzer 零改动

## 核心流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. 收集当天所有 WAV 文件（按时间排序）                              │
│    inbox/20260301120546.WAV                                      │
│    inbox/20260301132609.WAV                                      │
│    inbox/20260301154823.WAV                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. 合并成单个临时 WAV 文件                                         │
│    processing/2026-03-01-merged.wav                              │
│    （音频拼接，保持采样率/声道/位深一致）                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. 走现有 Pipeline（完全复用）                                     │
│    chunk → ASR → segment → classify → analyze → archive          │
│    - VAD Chunker 自动切分长音频                                   │
│    - SilenceSegmenter 根据静音自然分段                            │
│    - 说话人 ID 全天一致                                           │
└───────────────────────────────────────────────────────���─────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. 清理与归档                                                     │
│    - 删除临时合并文件                                             │
│    - 移动原始文件到 processed/2026-03-01/                         │
│    - 归档结果已在 archive/2026-03-01/                             │
└─────────────────────────────────────────────────────────────────┘
```

## 实现细节

### 1. 文件收集器

**位置**: `src/audio_journal/batch.py`

```python
import re
from datetime import datetime
from pathlib import Path

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
    """扫描 inbox，按日期分组并按时间排序。
    
    Returns:
        {"2026-03-01": [file1.wav, file2.wav, ...], ...}
    """
    groups: dict[str, list[tuple[datetime, Path]]] = {}
    
    for f in inbox.glob("*.wav"):
        ts = parse_recording_time(f.name)
        if ts is None:
            continue  # 跳过不符合命名规则的文件
        
        date_str = ts.strftime("%Y-%m-%d")
        groups.setdefault(date_str, []).append((ts, f))
    
    # 按日期排序，每天内部按时间排序
    return {
        date: [p for _, p in sorted(items)]
        for date, items in sorted(groups.items())
    }
```

### 2. 音频合并器

**位置**: `src/audio_journal/batch.py`

```python
import wave

def merge_wav_files(files: list[Path], output: Path) -> dict[str, Any]:
    """将多个 WAV 文件合并为一个。
    
    Args:
        files: 按时间排序的 WAV 文件列表
        output: 输出文件路径
    
    Returns:
        合并信息：{"total_frames": int, "duration_seconds": float, "file_count": int}
    
    Raises:
        ValueError: 文件参数不一致（采样率/声道/位深不同）
    """
    if not files:
        raise ValueError("没有文件可合并")
    
    # 读取第一个文件的参数
    with wave.open(str(files[0]), 'rb') as first:
        params = first.getparams()
        sample_rate = params.framerate
    
    total_frames = 0
    
    # 创建输出文件
    with wave.open(str(output), 'wb') as out:
        out.setparams(params)
        
        # 逐个写入
        for f in files:
            with wave.open(str(f), 'rb') as w:
                # 验证参数一致（采样率、声道数、采样宽度、压缩类型）
                if w.getparams()[:4] != params[:4]:
                    raise ValueError(
                        f"文件参数不匹配: {f.name}\n"
                        f"期望: {params[:4]}\n"
                        f"实际: {w.getparams()[:4]}"
                    )
                
                frames = w.readframes(w.getnframes())
                out.writeframes(frames)
                total_frames += w.getnframes()
    
    duration = total_frames / sample_rate
    
    return {
        "total_frames": total_frames,
        "duration_seconds": duration,
        "duration_minutes": duration / 60,
        "file_count": len(files),
        "sample_rate": sample_rate,
    }
```

### 3. 日级批处理器

**位置**: `src/audio_journal/batch.py`

```python
from audio_journal.config import AppConfig
from audio_journal.pipeline import Pipeline

class DailyBatchProcessor:
    """日级批处理器。"""
    
    def __init__(self, config: AppConfig, pipeline: Pipeline):
        self.config = config
        self.pipeline = pipeline
    
    async def process_day(self, date: str, files: list[Path]) -> DailyReport:
        """处理一天的所有录音文件。
        
        Args:
            date: YYYY-MM-DD
            files: 按时间排序的 WAV 文件列表
        
        Returns:
            处理报告
        """
        if not files:
            raise ValueError(f"日期 {date} 没有文件")
        
        # 1. 合并音频
        merged_path = self.config.paths.processing / f"{date}-merged.wav"
        merge_info = merge_wav_files(files, merged_path)
        
        try:
            # 2. 走现有 pipeline（完全复用，零改动）
            results = await self.pipeline.process(merged_path)
            
            # 3. 生成日报
            report = DailyReport(
                date=date,
                file_count=merge_info["file_count"],
                total_duration_minutes=merge_info["duration_minutes"],
                segment_count=len(results),
                scene_distribution=self._count_scenes(results),
                source_files=[f.name for f in files],
            )
            
            # 4. 移动原始文件到 processed/
            if self.config.batch.auto_move_processed:
                self._move_processed_files(date, files)
            
            return report
        
        finally:
            # 5. 清理临时合并文件
            if merged_path.exists():
                merged_path.unlink()
    
    def _count_scenes(self, results: list[AnalysisResult]) -> dict[str, int]:
        """统计场景分布。"""
        from collections import Counter
        return dict(Counter(r.scene.value for r in results))
    
    def _move_processed_files(self, date: str, files: list[Path]) -> None:
        """移动已处理文件到 processed/ 目录。"""
        dest_dir = self.config.batch.processed_dir / date
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        for f in files:
            dest = dest_dir / f.name
            f.rename(dest)
```

### 4. 日报模型

**位置**: `src/audio_journal/models/schemas.py`

```python
class DailyReport(BaseModel):
    """一天的处理报告。"""
    date: str                          # YYYY-MM-DD
    file_count: int                    # 原始 WAV 文件数
    total_duration_minutes: float      # 总录音时长（分钟）
    segment_count: int                 # 分析片段数
    scene_distribution: dict[str, int] # 场景分布 {"meeting": 3, "phone": 1}
    source_files: list[str]            # 原始文件名列表
```

### 5. 配置扩展

**改动文件**: `config.yaml` + `src/audio_journal/config.py`

```yaml
batch:
  auto_move_processed: true      # 处理完后将 WAV 移到 processed/ 目录
  processed_dir: ./data/processed
```

```python
class BatchConfig(BaseModel):
    auto_move_processed: bool = True
    processed_dir: Path = Path("./data/processed")

class AppConfig(BaseModel):
    # ... 现有字段 ...
    batch: BatchConfig = Field(default_factory=BatchConfig)
```

### 6. CLI 命令

**改动文件**: `src/audio_journal/cli.py`

```python
from datetime import date, timedelta
from audio_journal.batch import DailyBatchProcessor, collect_files_by_date

@main.command()
@click.option("--date", "target_date", type=str, default=None,
              help="处理指定日期，格式 YYYY-MM-DD。默认处理昨天。")
@click.pass_obj
def batch(obj: dict, target_date: str | None) -> None:
    """批量处理指定日期的所有录音。"""
    cfg: AppConfig = obj["config"]
    
    # 默认处理昨天
    if target_date is None:
        target_date = (date.today() - timedelta(days=1)).isoformat()
    
    # 收集文件
    files_by_date = collect_files_by_date(cfg.watcher.watch_dir)
    files = files_by_date.get(target_date, [])
    
    if not files:
        click.echo(f"📭 {target_date} 没有找到录音文件")
        return
    
    click.echo(f"🎙️  发现 {len(files)} 个录音文件 ({target_date})")
    for f in files:
        click.echo(f"  - {f.name}")
    
    # 处理
    pipe = create_pipeline(cfg)
    processor = DailyBatchProcessor(cfg, pipe)
    
    click.echo(f"\n⏳ 合并音频并处理...")
    report = asyncio.run(processor.process_day(target_date, files))
    
    click.echo(f"\n✅ 处理完成")
    click.echo(f"  文件数: {report.file_count}")
    click.echo(f"  时长: {report.total_duration_minutes:.1f} 分钟")
    click.echo(f"  片段数: {report.segment_count}")
    click.echo(f"  场景分布: {report.scene_distribution}")


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

## 目录结构

```
data/
├── inbox/                    # 新录音放这里
│   ├── 20260302120546.WAV
│   └── 20260302132609.WAV
├── processed/                # 处理完自动移过来
│   └── 2026-03-01/
│       ├── 20260301120546.WAV
│       └── 20260301132609.WAV
├── processing/               # 临时处理目录
│   ├── 2026-03-01-merged.wav  # 临时合并文件（处理完删除）
│   └── 2026-03-01/            # chunk 等中间文件
└── archive/                  # 归档结果
    └── 2026-03-01/
        ├── 001-meeting-项目进度.md
        ├── 002-phone-客户沟通.md
        └── index.jsonl
```

## 不改动的部分

**现有模块完全复用，零改动：**

| 模块 | 说明 |
|------|------|
| `Pipeline` | 完整流程不变 |
| `VADChunker` | 自动处理长音频（最长 4h/chunk） |
| `ASR` | 转写逻辑不变，说话人 ID 全天一致 |
| `SilenceSegmenter` | 根据静音自然分段 |
| `SceneClassifier` | 分类逻辑不变 |
| `MeetingAnalyzer` | 分析逻辑不变 |
| `LocalArchiver` | 归档逻辑不变 |
| `JSONLArchiveIndex` | 索引结构不变 |

## 实现顺序

| # | 任务 | 文件 | 代码量 |
|---|------|------|--------|
| 1 | 文件收集器 `parse_recording_time` + `collect_files_by_date` | batch.py (新) | ~40 行 |
| 2 | 音频合并器 `merge_wav_files` | batch.py | ~50 行 |
| 3 | `DailyBatchProcessor` + `DailyReport` | batch.py, schemas.py | ~60 行 |
| 4 | `BatchConfig` 配置 | config.py, config.yaml | ~10 行 |
| 5 | CLI `batch` + `batch-all` 命令 | cli.py | ~50 行 |
| 6 | 测试用例 | tests/test_batch.py (新) | ~100 行 |

**总计**: 新增 ~310 行代码，改动现有代码 0 行。

## 使用示例

```bash
# 处理昨天的录音
audio-journal batch

# 处理指定日期
audio-journal batch --date 2026-03-01

# 处理 inbox 中所有日期
audio-journal batch-all

# 查看归档结果
audio-journal list --date 2026-03-01
audio-journal show 20260301-001
```

## 常见问题

### Q: 一天 8 小时录音，合并后文件太大？

**A**: VAD Chunker 已经设计为处理长音频（最长 4 小时/会自动切分。合并文件只是临时的，处理完就删除。

### Q: 处理失败怎么办？

**A**: 原始文件保留在 `processed/`，可以重新运行 `batch --date` 命令。系统会重新合并和处理。

### Q: 文件间有长时间间隔（如中午休息 2 小时）会怎样？

**A**: SilenceSegmenter 会在长静音处（默认 30 秒）自然切分，不会把上午和下午的会议合并成一个片段。

### Q: 如果某个文件的采样率不一致怎么办？

**A**: `merge_wav_files` 会检测参数不一致并抛出错误，提示用户检查录音设备设置。

### Q: 说话人 ID 真的能全天一致吗？

**A**: 是的。因为 ASR 引擎处理的是合并后的单个音频流，说话人识别模型会在整个音频上建立一致的 speaker embedding，SPEAKER_00 在全天都是同一个人。

### Q: 如果想保留实时处理模式怎么办？

**A**: 现有的 `audio-journal process <file.wav>` 和 `audio-journal start` 命令保持不变，可以继续使用。批处理模式是新增功能，不影响原有功能。

## 未来扩展（不在本次范围）

- **日报生成** — 生成 `daily-report.md` 作为当天的索引页
- **cron 自动触发** — 每天凌晨自动执行 `batch --date yesterday`
- **并行处理多天** — `batch-all` 支持多进程并行处理不同日期
- **增量处理** — 检测 `processed/` 目录，跳过已处理的日期

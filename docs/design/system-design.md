# Audio Journal — 个人全天候录音分析系统

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将每日佩戴录音设备采集的长时间音频，自动转写、智能分段、场景分类、内容分析，经用户 CLI 确认后归档到本地或 Obsidian。

**Architecture:** 全自动后台服务 + 管理 CLI。文件监听器检测新录音后自动触发完整 Pipeline：音频预切分 → 本地 ASR（含说话人识别）→ 文本分段 → 场景分类 → 场景专用分析 → 自动归档。无需人工确认，通过持续优化 prompt 和参数提升质量。

**Tech Stack:** Python 3.11+, 本地 ASR (FunASR/WhisperX + diarization), 云端 LLM API (多模型抽象层), Click (CLI), Pydantic (数据模型), watchdog (文件监听)

---

## 1. 系统架构

### 1.1 整体流程

```
┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐    ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
│ Watcher │───▶│  WAV     │───▶│ 音频预切分│───▶│  ASR    │───▶│  分段器  │───▶│ 场景分类  │───▶│ 分析Agent │───▶│ 自动归档 │
│ 文件监听 │    │  音频    │    │ Chunker  │    │ +说话人  │    │Segmenter│    │ Router   │    │ Analyzer │    │ Archive │
└─────────┘    └──────────┘    └──────────┘    └─────────┘    └─────────┘    └──────────┘    └──────────┘    └─────────┘
```

#### 长录音预切分策略

长时间录音（数小时）不能直接喂给 ASR + 说话人识别模型，原因：
1. **内存爆炸** — 大多数 diarization 模型设计用于 30min-2h 音频
2. **说话人漂移** — 同一人早晚声纹特征有差异，长音频识别准确度下降
3. **跨段不一致** — 分块处理时 speaker ID 在不同块间不一致

**解决方案：音频级预切分（Chunker）**

在 ASR 之前，先用 VAD（语音活动检测）按长静音间隔将原始 WAV 切成 10 分钟 - 4 小时的 chunk，每个 chunk 独立走完整 pipeline：

```
原始 WAV (8h)
  ↓ 音频预切分 (VAD/静音检测, 可配置静音阈值)
  ↓
chunk_001.wav (3h 15m) → ASR+说话人 → 分段 → 分类 → 分析
chunk_002.wav (2h 30m) → ASR+说话人 → 分段 → 分类 → 分析
chunk_003.wav (1h 45m) → ASR+说话人 → 分段 → 分类 → 分析
...
  ↓
所有分析结果汇总 → 自动归档
```

**优势：**
- 内存可控，每次只处理一个 chunk
- 各 chunk 可并行处理，加速整体流程
- 说话人识别在 chunk 粒度上准确度高

**代价：**
- 跨 chunk 的说话人关联（"chunk1 的 SPEAKER_01 和 chunk3 的 SPEAKER_02 是同一个人"）在 MVP 阶段不做，作为 Phase 3 优化项
- 如果一段对话刚好跨切分点会被拆成两段（但预切分按长静音切，正常对话中不太会有超过阈值的静音，误切概率很低）

### 1.2 目录结构

```
audio-journal/
├── pyproject.toml              # 项目配置 (使用 uv/poetry)
├── config.yaml                 # 运行时配置（ASR模型、LLM API keys、场景定义等）
├── src/
│   └── audio_journal/
│       ├── __init__.py
│       ├── cli.py              # CLI 入口 (Click)
│       ├── config.py           # 配置加载 (Pydantic Settings)
│       ├── pipeline.py         # Pipeline 编排器
│       ├── watcher/
│       │   ├── __init__.py
│       │   └── file_watcher.py # 文件监听服务 (watchdog)
│       ├── chunker/
│       │   ├── __init__.py
│       │   └── vad_chunker.py  # 基于 VAD/静音检测的音频预切分
│       ├── asr/
│       │   ├── __init__.py
│       │   ├── base.py         # ASR 抽象基类
│       │   ├── funasr.py       # FunASR 实现
│       │   └── whisperx.py     # WhisperX 实现
│       ├── segmenter/
│       │   ├── __init__.py
│       │   └── silence.py      # 基于静音/时间间隔的分段器
│       ├── classifier/
│       │   ├── __init__.py
│       │   └── scene.py        # 场景分类器 (LLM-based)
│       ├── analyzer/
│       │   ├── __init__.py
│       │   ├── base.py         # 分析器抽象基类
│       │   ├── meeting.py      # 工作会议分析
│       │   ├── business.py     # 商务拜访分析
│       │   ├── idea.py         # 灵感/自言自语分析
│       │   ├── learning.py     # 学习/视频分析
│       │   ├── phone.py        # 电话通话分析
│       │   └── chat.py         # 闲聊分析（含价值检测）
│       ├── llm/
│       │   ├── __init__.py
│       │   ├── base.py         # LLM Provider 抽象基类 + 工厂
│       │   └── openai_compat.py# OpenAI Chat Completions 兼容实现（openai/deepseek/z.ai）
│       ├── archiver/
│       │   ├── __init__.py
│       │   ├── local.py        # 本地文件归档
│       │   └── obsidian.py     # Obsidian vault 归档
│       └── models/
│           ├── __init__.py
│           └── schemas.py      # Pydantic 数据模型
├── prompts/
│   ├── classifier.txt          # 场景分类 prompt
│   ├── meeting.txt             # 工作会议分析 prompt
│   ├── business.txt            # 商务拜访分析 prompt
│   ├── idea.txt                # 灵感分析 prompt
│   ├── learning.txt            # 学习分析 prompt
│   ├── phone.txt               # 电话通话分析 prompt
│   └── chat.txt                # 闲聊分析 prompt (含价值检测)
├── data/
│   ├── inbox/                  # 待处理的 WAV 文件放这里
│   ├── processing/             # 处理中的中间文件
│   ├── transcripts/            # ASR 转写结果
│   ├── analysis/               # 分析结果（待确认）
│   └── archive/                # 已确认归档的本地文件
└── tests/
    ├── test_segmenter.py
    ├── test_classifier.py
    ├── test_analyzer.py
    └── test_pipeline.py
```

---

## 2. 核心模块设计

### 2.1 数据模型 (`models/schemas.py`)

```python
from pydantic import BaseModel
from enum import Enum
from datetime import datetime

class SceneType(str, Enum):
    MEETING = "meeting"           # 工作会议
    BUSINESS = "business"         # 商务拜访
    IDEA = "idea"                 # 灵感/自言自语
    LEARNING = "learning"         # 学习/观看视频
    PHONE = "phone"               # 电话通话
    CHAT = "chat"                 # 朋友闲聊

class Speaker(BaseModel):
    id: str                       # 说话人标识 (SPEAKER_00, SPEAKER_01...)
    label: str | None = None      # 用户标注的名字（可选）

class Utterance(BaseModel):
    """ASR 转写的单条发言"""
    speaker: Speaker
    text: str
    start_time: float             # 秒
    end_time: float               # 秒

class Segment(BaseModel):
    """分段后的一个片段"""
    id: str                       # 唯一标识
    utterances: list[Utterance]
    start_time: float
    end_time: float
    duration: float               # 秒
    source_file: str              # 原始 WAV 文件名

class ClassifiedSegment(Segment):
    """分类后的片段"""
    scene: SceneType
    confidence: float             # 分类置信度
    value_tags: list[str] = []    # 价值标签（投融资/技术/市场等）

class AnalysisResult(BaseModel):
    """分析结果"""
    segment_id: str
    scene: SceneType
    summary: str                  # 摘要
    key_points: list[str]         # 关键要点
    action_items: list[str] = []  # 待办事项（会议/商务场景）
    participants: list[str] = []  # 参与者
    topics: list[str] = []       # 话题标签
    value_level: str = "normal"   # high / normal / low
    raw_text: str                 # 原始转写文本
    metadata: dict = {}           # 场景特定的额外字段

class ReviewDecision(str, Enum):
    ACCEPT = "accept"             # 确认归档
    EDIT = "edit"                 # 编辑后归档
    SKIP = "skip"                 # 跳过（不归档）
    DISCARD = "discard"           # 丢弃

class ArchiveTarget(str, Enum):
    LOCAL = "local"               # 本地 markdown
    OBSIDIAN = "obsidian"         # Obsidian vault
```

### 2.2 ASR 模块 (`asr/`)

抽象基类：

```python
class ASREngine(ABC):
    @abstractmethod
    def transcribe(self, audio_path: str) -> list[Utterance]:
        """转写音频文件，返回带说话人标签和时间戳的发言列表"""
        ...
```

两个实现：
- `FunASREngine` — 阿里达摩院 FunASR，原生支持中文 + 说话人识别，推荐首选
- `WhisperXEngine` — WhisperX + pyannote，英文更强，中文需要额外调优

配置选择哪个引擎：

```yaml
asr:
  engine: funasr          # funasr | whisperx
  model: paraformer-zh    # ASR 模型
  device: mps             # mps (Apple Silicon) | cpu | cuda
  batch_size: 4
  language: zh
```

### 2.3 分段器 (`segmenter/`)

基于静音间隔 + 时间窗口的分段策略：

```python
class SilenceSegmenter:
    def __init__(self, config: SegmenterConfig):
        self.min_silence_gap: float = 30.0    # 超过30秒静音视为分段点
        self.max_segment_duration: float = 1800.0  # 单段最长30分钟
        self.min_segment_duration: float = 10.0    # 低于10秒的段丢弃

    def segment(self, utterances: list[Utterance], source_file: str) -> list[Segment]:
        """将连续的发言按静音间隔切分为独立片段"""
        ...
```

分段逻辑：
1. 遍历 utterances，计算相邻发言的时间间隔
2. 间隔 > `min_silence_gap` → 切分
3. 单段累计时长 > `max_segment_duration` → 强制切分（在最近的静音点）
4. 过滤掉时长 < `min_segment_duration` 的碎片段

### 2.4 场景分类器 (`classifier/`)

两层分类架构：

```python
class SceneClassifier:
    async def classify(self, segment: Segment) -> ClassifiedSegment:
        """
        第一层：场景分类 — 判断属于6个场景中的哪个
        第二层：价值检测 — 对闲聊场景，扫描是否包含高价值话题
        """
        # 1. 提取片段的前N条发言作为样本
        sample_text = self._extract_sample(segment)

        # 2. 调用 LLM 进行场景分类
        scene, confidence = await self._classify_scene(sample_text)

        # 3. 如果是闲聊场景，进行价值检测
        value_tags = []
        if scene == SceneType.CHAT:
            value_tags = await self._detect_value(sample_text)

        return ClassifiedSegment(
            **segment.model_dump(),
            scene=scene,
            confidence=confidence,
            value_tags=value_tags,
        )
```

分类 prompt 设计要点（`prompts/classifier.txt`）：

```
你是一个音频内容场景分类器。根据以下转写文本片段，判断它属于哪个场景：

1. meeting — 工作会议（多人讨论工作事项、项目进展、技术方案）
2. business — 商务拜访（客户/供应商/渠道/合作方的正式或半正式交流）
3. idea — 灵感/自言自语（个人思考、灵感记录、自我对话）
4. learning — 学习/观看视频（听课、看视频、阅读讨论）
5. phone — 电话通话（电话交流，通常只有两个说话人）
6. chat — 朋友闲聊（非工作的社交对话）

判断依据：说话人数量、对话语气、内容主题、正式程度。

输出 JSON：
{"scene": "<scene_type>", "confidence": 0.0-1.0, "reasoning": "简短理由"}
```

价值检测 prompt（闲聊场景专用）：

```
以下是一段闲聊对话。请检测其中是否包含以下高价值话题：
- 投融资信息（融资、投资、估值、上市）
- 技术讨论（架构、算法、新技术、工具）
- 市场解读（行业趋势、竞争分析、市场机会）
- 人脉信息（关键人物、组织变动、合作机会）
- 商业洞察（商业模式、盈利策略、成本分析）

如果包含，输出相关标签；如果纯闲聊无价值内容，输出空列表。

输出 JSON：
{"value_tags": ["tag1", "tag2"], "has_value": true/false}
```

### 2.5 场景分析器 (`analyzer/`)

每个场景对应一个专用分析器，共享抽象基类：

```python
class BaseAnalyzer(ABC):
    def __init__(self, llm: LLMProvider, prompt_path: str):
        self.llm = llm
        self.prompt = self._load_prompt(prompt_path)

    @abstractmethod
    async def analyze(self, segment: ClassifiedSegment) -> AnalysisResult:
        ...
```

各场景分析器的输出重点：

| 场景 | 核心输出 | 额外字段 |
|------|---------|---------|
| meeting | 决策、待办、责任人、时间节点 | `decisions`, `deadlines` |
| business | 关键诉求、承诺、跟进事项 | `commitments`, `follow_ups` |
| idea | 核心想法、主题标签 | `idea_type` (灵感/反思/计划) |
| learning | 知识点摘要、个人笔记 | `source_type` (视频/课程/阅读) |
| phone | 对方诉求、约定事项 | `caller_intent` |
| chat | 高价值片段提取 | `value_tags`, `extracted_insights` |

Router 逻辑：

```python
class AnalyzerRouter:
    def __init__(self, analyzers: dict[SceneType, BaseAnalyzer]):
        self.analyzers = analyzers

    async def route(self, segment: ClassifiedSegment) -> AnalysisResult:
        analyzer = self.analyzers[segment.scene]
        return await analyzer.analyze(segment)
```

### 2.6 LLM 抽象层 (`llm/`)

```python
class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        ...

class LLMFactory:
    """根据配置创建 Provider，并支持按 stage 覆盖。"""

    @staticmethod
    def create(cfg: LLMConfig, stage: str | None = None) -> LLMProvider:
        eff = getattr(cfg.overrides, stage, None) if stage else None
        eff = eff or cfg
        provider = eff.provider

        # Phase 1 MVP: 仅实现 OpenAI Chat Completions 兼容协议（OpenAI/DeepSeek/z.ai）。
        if provider in {"openai", "deepseek", "zai"}:
            return OpenAICompatibleProvider(...)

        # 如果 stage override 指定了未实现 provider（例如 claude），回退到主配置。
        ...
```

配置：

```yaml
llm:
  provider: deepseek        # openai | deepseek | zai
  model: deepseek-chat      # 具体模型名
  api_key_env: DEEPSEEK_API_KEY  # 从环境变量读取（z.ai 推荐 ZHIPUAI_API_KEY）
  # base_url: https://api.deepseek.com/v1  # 可选：不填使用内置默认值；zai 默认 https://open.bigmodel.cn/api/paas/v4/
  temperature: 0.3
  max_tokens: 4096

  # 可选：不同阶段用不同模型
  overrides:
    classifier:
      provider: deepseek
      model: deepseek-chat   # 分类用便宜快速的模型
    analyzer:
      provider: zai
      model: glm-4-plus
      api_key_env: ZHIPUAI_API_KEY
```

### 2.7 CLI 确认 (`reviewer/`)

```
$ audio-journal review

📅 2026-02-26 录音分析结果 (12 个片段)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1/12] 🏢 工作会议 | 09:15-10:32 (1h17m) | 置信度: 0.95
说话人: SPEAKER_00 (你), SPEAKER_01, SPEAKER_02

📝 摘要:
讨论了 FP-Enhancement 项目的实验方案，确认由开发部门推进...

🔑 关键要点:
  • 实验方案由开发部门推进，预计下周一出材料
  • 服务端归并 + IP 高权重方向已确认
  • ...

📋 待办:
  • [开发部门] 3/2 前提交实验报告
  • [ipieces] 跟进实验结果

操作: [a]确认 [e]编辑 [s]跳过 [d]丢弃 [v]查看原文 [q]退出 >
```

### 2.8 归档 (`archiver/`)

本地归档：

```
data/archive/
└── 2026-02-26/
    ├── 001-meeting-fp-enhancement讨论.md
    ├── 002-phone-供应商沟通.md
    └── 003-idea-产品方向思考.md
```

Obsidian 归档（写入 vault 指定目录）：

```yaml
archive:
  obsidian:
    vault_path: /Users/m4006/.openclaw/workspace/opsidian
    base_dir: AudioJournal          # vault 内的归档目录
    template: |                     # 归档模板
      ---
      date: {{date}}
      scene: {{scene}}
      duration: {{duration}}
      speakers: {{speakers}}
      tags: {{topics}}
      ---
      # {{title}}

      ## 摘要
      {{summary}}

      ## 关键要点
      {{key_points}}

      ## 待办事项
      {{action_items}}

      ## 原始转写
      > {{raw_text}}
```

---

## 3. Pipeline 编排

```python
class Pipeline:
    def __init__(self, config: Config):
        self.chunker = VADChunker(config.chunker)
        self.asr = ASRFactory.create(config.asr)
        self.segmenter = SilenceSegmenter(config.segmenter)
        self.classifier = SceneClassifier(config.classifier, llm)
        self.router = AnalyzerRouter(analyzers)
        self.archiver = ArchiverFactory.create(config.archive)

    async def process(self, audio_path: str) -> list[AnalysisResult]:
        # Step 0: 音频预切分（长录音 → 多个 chunk）
        chunks = self.chunker.split(audio_path)

        all_results = []
        for chunk in chunks:
            # Step 1: ASR 转写（含说话人识别）
            utterances = self.asr.transcribe(chunk.path)

            # Step 2: 文本分段
            segments = self.segmenter.segment(utterances, chunk.path)

            # Step 3: 场景分类
            classified = [await self.classifier.classify(seg) for seg in segments]

            # Step 4: 场景分析（可并发）
            results = await asyncio.gather(*[
                self.router.route(seg) for seg in classified
            ])
            all_results.extend(results)

        # Step 5: 自动归档（无需人工确认）
        archived = self.archiver.archive_all(all_results)
        logger.info(f"已自动归档 {len(archived)} 条结果")

        return all_results


class FileWatcher:
    """监听目录，检测新音频文件并触发 Pipeline"""
    def __init__(self, config: Config, pipeline: Pipeline):
        self.watch_dir = config.paths.inbox
        self.pipeline = pipeline

    def start(self):
        """启动文件监听服务"""
        observer = Observer()
        handler = AudioFileHandler(self.pipeline)
        observer.schedule(handler, self.watch_dir, recursive=False)
        observer.start()
        logger.info(f"监听目录: {self.watch_dir}")

class AudioFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith('.wav'):
            # 等待文件写入完成
            self._wait_stable(event.src_path)
            asyncio.run(self.pipeline.process(event.src_path))
```

---

## 4. CLI 命令设计

```bash
# 服务管理
audio-journal start                      # 启动文件监听服务（前台）
audio-journal start -d                   # 后台守护进程模式
audio-journal stop                       # 停止服务

# 查看状态
audio-journal status                     # 服务状态 + 处理统计

# 查看归档结果
audio-journal list                       # 列出最近归档
audio-journal list --date 2026-02-26     # 按日期
audio-journal list --scene meeting       # 按场景
audio-journal show <id>                  # 查看某条详情

# 重新处理
audio-journal reprocess <id>             # 重新分析某条（用最新 prompt）
audio-journal reprocess --date 2026-02-26  # 重新处理某天全部

# 手动触发（不依赖 watcher）
audio-journal process <file.wav>         # 手动处理指定文件

# 配置管理
audio-journal config show                # 显示当前配置
audio-journal config set llm.provider zai  # 修改配置
```

---

## 5. 配置文件 (`config.yaml`)

```yaml
# ASR 配置
asr:
  engine: funasr
  model: paraformer-zh
  vad_model: fsmn-vad       # 语音活动检测
  punc_model: ct-punc       # 标点恢复
  spk_model: cam++          # 说话人识别
  device: mps
  batch_size: 4

# 音频预切分配置
chunker:
  min_silence_gap: 30       # 秒，预切分静音阈值（可自定义）
  max_chunk_duration: 14400 # 秒，单个 chunk 最长 4 小时（覆盖长会议场景）
  min_chunk_duration: 60    # 秒，低于 1 分钟的 chunk 合并到相邻 chunk
  parallel: true            # 是否并行处理多个 chunk
  max_workers: 4            # 并行处理的最大 worker 数

# 分段配置
segmenter:
  min_silence_gap: 30       # 秒，静音分段阈值
  max_segment_duration: 1800 # 秒，单段最长
  min_segment_duration: 10   # 秒，最短有效段

# LLM 配置
llm:
  provider: deepseek  # openai | deepseek | zai
  model: deepseek-chat
  api_key_env: DEEPSEEK_API_KEY  # z.ai 推荐 ZHIPUAI_API_KEY
  # base_url: https://api.deepseek.com/v1  # 可选：不填使用内置默认值；zai 默认 https://open.bigmodel.cn/api/paas/v4/
  temperature: 0.3
  overrides:
    classifier:
      provider: deepseek
      model: deepseek-chat
    analyzer:
      provider: zai
      model: glm-4-plus
      api_key_env: ZHIPUAI_API_KEY

# 场景配置
scenes:
  - meeting
  - business
  - idea
  - learning
  - phone
  - chat

# 归档配置
archive:
  default_target: local
  local:
    base_dir: ./data/archive
  obsidian:
    vault_path: /path/to/obsidian/vault
    base_dir: AudioJournal

# 路径配置
paths:
  inbox: ./data/inbox
  processing: ./data/processing
  transcripts: ./data/transcripts
  analysis: ./data/analysis
  prompts: ./prompts

# 文件监听配置
watcher:
  watch_dir: ./data/inbox       # 监听目录
  patterns: ["*.wav"]           # 监听的文件类型
  stable_seconds: 5             # 文件写入稳定等待时间（秒）
  daemon: false                 # 是否以守护进程运行
```

---

## 6. 实现计划（分阶段）

### Phase 1: MVP — 核心流程跑通
1. 项目脚手架（pyproject.toml, 目录结构, config 加载）
2. 数据模型定义（Pydantic schemas）
3. LLM 抽象层（至少实现一个 provider）
4. 音频预切分器（VAD Chunker，支持可配置静音阈值）
5. ASR 模块（先实现一个引擎）
6. 分段器
7. 场景分类器
8. 一个场景分析器（先做 meeting）
9. 自动归档（本地）
10. 文件监听服务（watchdog）
11. Pipeline 编排 + `audio-journal start` 命令
12. 管理 CLI（status/list/show）

### Phase 2: 完善场景 + 归档
13. 剩余 5 个场景分析器
14. 闲聊价值检测（二层分类）
15. Obsidian 归档
16. 第二个 ASR 引擎
17. 第二个 LLM provider
18. reprocess 命令（用最新 prompt 重新分析）

### Phase 3: 优化体验
19. 长音频 chunk 并行处理
20. 处理进度日志
21. 分析结果缓存（避免重复处理）
22. 说话人标注记忆（SPEAKER_01 = 张三）
23. 跨 chunk 说话人关联（声纹嵌入聚类）
24. 守护进程模式 + 开机自启

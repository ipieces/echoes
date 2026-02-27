# Audio Journal - Phase 1 MVP 详细实现计划（TDD）

本文档是 `audio-journal` 项目 **Phase 1 MVP（12 个 task）** 的详细实现计划：以最小可运行闭环为目标，跑通「文件监听 → 预切分 → ASR（含说话人）→ 分段 → 场景分类 → 会议分析 → 本地归档 → 管理 CLI」。

约束：
- 只写计划，不写代码。
- 以测试驱动（TDD）组织：每个 task 先列测试，再列实现。
- 标注依赖关系与可并行的部分。

---

## 0. 范围与关键决策

### 0.1 Phase 1 目标（Definition of Done）
- 在本机把一个 `*.wav` 放入 `data/inbox/`：服务能检测到新文件并自动处理。
- 产出可查询的归档：生成 Markdown 归档文件 + 索引（用于 `list/show/status`）。
- CLI 至少支持：`process`（手动处理单文件）、`start`（前台监听）、`status/list/show`（管理查询）。

### 0.2 Phase 1 非目标（明确不做）
- 不做跨 chunk 说话人关联、缓存去重、并行处理调度优化（Phase 3）。
- 不做 Obsidian 归档（Phase 2）。
- 不强求 `start -d/stop` 守护进程模式（Phase 3）；Phase 1 只做前台 `start`。

### 0.3 技术选型（具体）
- **Python**：3.11+
- **包管理/构建**：`uv`（开发体验快；后续可切 poetry 但不建议在 MVP 阶段折腾）
- **CLI**：`click`（与设计文档一致，且 `click.testing.CliRunner` 易测）
- **数据模型**：`pydantic>=2` + `pydantic-settings`
- **配置**：`PyYAML` 读取 `config.yaml`，再映射到 Pydantic Settings
- **HTTP/LLM**：`httpx`（异步）+ `respx`（单测 mock）
- **文件监听**：`watchdog`
- **测试**：`pytest` + `pytest-asyncio`
- **格式/质量（建议）**：`ruff`（可先加到 `pyproject.toml`，不阻塞功能）

### 0.4 设计落地的简化策略（保证 TDD 可行）
- **外部依赖（LLM/ASR）单测不直连**：单元测试通过 fake/stub + HTTP mock 完成；真实模型走 `integration` 标记测试（可选）。
- **Chunker 的 VAD**：MVP 用「能量/静音检测」实现（仅支持 PCM WAV），满足"静音阈值切分"的设计目标；后续可替换成模型 VAD（FunASR VAD/Silero）。
- **存储/索引**：MVP 用文件系统 + JSONL 索引（无需 DB），支持 `list/show/status`。

---

## 1. 建议目录与代码骨架（Phase 1 要创建）

项目根目录：`/Users/m4006/.openclaw/workspace/audio-journal/`

建议骨架（与 `system-design.md` 一致，少量补充 storage/utils）：

- `pyproject.toml`
- `config.yaml`
- `src/audio_journal/__init__.py`
- `src/audio_journal/cli.py`
- `src/audio_journal/config.py`
- `src/audio_journal/pipeline.py`
- `src/audio_journal/models/schemas.py`
- `src/audio_journal/llm/base.py`
- `src/audio_journal/llm/openai_compat.py`（DeepSeek/OpenAI 兼容实现）
- `src/audio_journal/chunker/vad_chunker.py`
- `src/audio_journal/asr/base.py`
- `src/audio_journal/asr/funasr.py`（可选：真实集成）
- `src/audio_journal/asr/mock.py`（测试/开发用）
- `src/audio_journal/segmenter/silence.py`
- `src/audio_journal/classifier/scene.py`
- `src/audio_journal/analyzer/base.py`
- `src/audio_journal/analyzer/meeting.py`
- `src/audio_journal/archiver/local.py`
- `src/audio_journal/storage/index.py`（JSONL 索引读写）
- `src/audio_journal/watcher/file_watcher.py`

数据目录（运行时）：
- `data/inbox/`
- `data/processing/`
- `data/transcripts/`
- `data/analysis/`
- `data/archive/`

Prompt 目录（可从设计文档直接落文件）：
- `prompts/classifier.txt`
- `prompts/meeting.txt`

测试目录：
- `tests/`（按模块拆分）
- `tests/fixtures/`（示例 transcript/LLM 返回 JSON）

---

## 2. Task 依赖关系与并行建议

### 2.1 依赖图（必须串行的主链）
- Task 1（脚手架/配置） → Task 2（数据模型） → Task 3（LLM） → Task 7（分类器） → Task 8（meeting 分析器） → Task 9（归档） → Task 11（Pipeline+start） → Task 12（管理 CLI）

### 2.2 可并行的任务
- Task 4（Chunker）、Task 5（ASR）、Task 6（Segmenter）、Task 10（Watcher）在 Task 1/2 完成后可并行推进。

---

## 3. Phase 1 MVP - 12 个 Task 详细计划（TDD）

以下每个 task 都包含：目标、依赖、文件与代码结构、测试优先步骤、实现步骤、验证方式。

---

### Task 1/12 - 项目脚手架与配置加载

目标：建立可安装、可运行、可测试的 Python 包；实现 `config.yaml` → Pydantic 配置对象加载。

依赖：无。

产出文件：
- `pyproject.toml`
- `config.yaml`
- `src/audio_journal/config.py`
- `src/audio_journal/__init__.py`
- `tests/test_config.py`

代码结构建议：
- `audio_journal.config`
  - `AppConfig`（根配置，包含 asr/chunker/segmenter/llm/paths/archive/watcher 等子配置）
  - `load_config(path: str | Path) -> AppConfig`
  - `resolve_paths()`（把相对路径基于项目根或 config 文件所在目录展开）

TDD（先写测试）：
1. `tests/test_config.py`
   - `test_load_config_defaults_and_paths(tmp_path)`：
     - 给一个最小 `config.yaml`（写到 tmp_path）
     - 断言能加载成功、字段类型正确、路径被正确解析为绝对/规范化路径
   - `test_load_config_env_api_key(monkeypatch, tmp_path)`：
     - 设置 `DEEPSEEK_API_KEY` 环境变量
     - 断言 `llm.api_key`（或运行时取 env 的方法）可用

实现步骤：
1. 确定配置字段（以 `docs/system-design.md` 的 `config.yaml` 为基准）。
2. `load_config()`：读取 YAML → dict → Pydantic 校验。
3. 明确「密钥读取策略」：仅存 `api_key_env`，运行时从 env 读取；配置对象中不要持久化明文密钥。
4. 在 `pyproject.toml` 配置 console script：`audio-journal = audio_journal.cli:main`（先占位，Task 12 完成 CLI 后可真正可用）。

验证步骤：
- 运行：`uv run pytest -q`
- 手动：在项目根放一个 `config.yaml`，调用一个最小脚本/REPL（后续由 CLI 覆盖）能打印出解析后的 `paths.inbox`。

---

### Task 2/12 - 数据模型定义（Pydantic schemas）

目标：实现贯穿全链路的数据结构（Utterance/Segment/ClassifiedSegment/AnalysisResult 等），并保证序列化稳定。

依赖：Task 1。

产出文件：
- `src/audio_journal/models/schemas.py`
- `tests/test_schemas.py`

关键设计点（落地建议）：
- 保持与 `docs/system-design.md` 接近，但允许补充细粒度结构以避免信息丢失：
  - 增加 `ActionItem`（task/owner/deadline）模型，meeting 分析时可落地
  - `AnalysisResult.metadata: dict[str, Any]` 保存场景专属字段（如 decisions）

TDD：
1. `tests/test_schemas.py`
   - `test_utterance_segment_roundtrip()`：构造 utterances → segment → `model_dump_json()` → `model_validate_json()`，断言等价
   - `test_analysis_result_accepts_metadata()`：metadata 可包含嵌套 dict/list

实现步骤：
1. 在 `schemas.py` 中定义：
   - `SceneType`（meeting/business/idea/learning/phone/chat）
   - `Speaker`、`Utterance`、`Segment`、`ClassifiedSegment`
   - `ActionItem`（可选但建议）
   - `AnalysisResult`
2. 统一时间字段：
   - Utterance/Segment 用 `float` 秒
   - 归档展示用格式化函数（后续在 CLI 做）

验证步骤：
- `uv run pytest -q tests/test_schemas.py`

---

### Task 3/12 - LLM 抽象层（至少 1 个 provider）

目标：实现 `LLMProvider` 抽象 + 1 个可用实现（OpenAI-compatible），支持「prompt + system + JSON 输出」模式；并能被分类器/分析器复用。

依赖：Task 1、Task 2。

产出文件：
- `src/audio_journal/llm/base.py`
- `src/audio_journal/llm/openai_compat.py`
- `tests/test_llm_provider.py`

实现范围建议：
- 先实现一个 `OpenAICompatibleProvider`：可用于 DeepSeek/OpenAI（同一协议，不同 base_url/model/api_key）。
- `LLMFactory.create(config, stage=None)`：支持 `overrides.classifier`、`overrides.analyzer`。
- 输出解析：提供 `parse_json_strict(text) -> dict`，对"前后夹杂多余文本"的情况做最小容错（但仍以严格 JSON 为主）。

TDD：
1. `tests/test_llm_provider.py`
   - 使用 `respx` mock `POST /chat/completions`
   - `test_llm_complete_returns_text()`：断言返回字符串
   - `test_llm_complete_json_mode_and_parse()`：mock 返回 `{"scene":"meeting","confidence":0.9,"reasoning":"..."}`，断言能解析成 dict
   - `test_llm_factory_overrides()`：当 stage=classifier/analyzer 时选择不同 model/provider

实现步骤：
1. 在 `LLMProvider.complete()` 里统一接口（异步）。
2. 在 `OpenAICompatibleProvider` 中实现：
   - headers：Bearer token
   - payload：messages + model + temperature + max_tokens + （可选）response_format JSON
3. 增加超时与重试策略（MVP 只做超时；重试可后置）。

验证步骤：
- `uv run pytest -q tests/test_llm_provider.py`
- （可选手动）设置 env key，跑一个小脚本调用 deepseek 分类 prompt，确认返回 JSON。

---

### Task 4/12 - 音频预切分器（Chunker：静音/VAD）

目标：在 ASR 之前把超长 WAV 切成多个 chunk；按静音阈值切分，并支持 max/min chunk duration 配置。

依赖：Task 1、Task 2（用配置模型；chunk 输出可用简单 dataclass）。

产出文件：
- `src/audio_journal/chunker/vad_chunker.py`
- `tests/test_chunker.py`

实现策略（MVP 友好）：
- 仅支持 **PCM WAV**（单元测试可用 `wave` 模块生成），避免引入 ffmpeg。
- 静音检测：滑窗计算 RMS/能量，低于阈值视为静音；连续静音超过 `min_silence_gap` 作为切分点。
- 保底策略：即使没有足够静音，也按 `max_chunk_duration` 强制切。

TDD：
1. `tests/test_chunker.py`
   - `test_chunker_splits_on_long_silence(tmp_path)`：生成"音频(10s tone) + 静音(40s) + 音频(10s tone)"的 wav，断言输出 2 个 chunk，且边界在静音附近
   - `test_chunker_enforces_max_duration(tmp_path)`：设置 `max_chunk_duration=15`（秒，测试用小值），生成 30s 连续音频，断言强制切成 2 个 chunk（注意：生产默认值为 14400s 即 4 小时，覆盖长会议场景）
   - `test_chunker_merges_too_short_chunk(tmp_path)`：设置 `min_chunk_duration=3s`，构造 2s 小碎片，断言被合并到相邻 chunk

实现步骤：
1. `VADChunker.split(audio_path) -> list[Chunk]`
   - `Chunk` 至少包含：`path/start_time/end_time/duration`（时间以秒）
2. 读取 WAV：用 `wave` + `array`/`numpy`（二选一；MVP 可不用 numpy）
3. 静音检测：
   - 固定帧长（如 30ms）滑窗算能量/RMS
   - 低于阈值认为静音；累计静音超过 `min_silence_gap` 记为切点
4. 输出 chunk WAV：写到 `paths.processing/<stem>/chunks/chunk_001.wav`（目录由 pipeline 创建）

验证步骤：
- `uv run pytest -q tests/test_chunker.py`
- （手动）用 `audio-journal process data/inbox/sample.wav`，确认 `data/processing/.../chunks/` 产出多个 wav

---

### Task 5/12 - ASR 模块（先实现一个引擎）

目标：实现 ASR 抽象接口与一个可用引擎。

依赖：Task 1、Task 2。

产出文件：
- `src/audio_journal/asr/base.py`
- `src/audio_journal/asr/mock.py`（用于测试/本地快速跑通）
- `src/audio_journal/asr/funasr.py`（可选：真实集成，建议作为 integration）
- `tests/test_asr_mock.py`
- `tests/test_asr_funasr_integration.py`（可选）

实现策略：
- 单测默认使用 `MockASREngine`：从 fixtures 读取"已转写结果 JSON"，返回 `list[Utterance]`。
- `FunASREngine`：把真实依赖隔离为 optional extra（例如 `pip install .[asr-funasr]`），避免污染基础开发。

TDD：
1. `tests/test_asr_mock.py`
   - `test_mock_asr_loads_fixture()`：给定 fixture JSON，返回 utterances 数量与字段正确（speaker/text/start/end）
2. `tests/test_asr_funasr_integration.py`（标记 `@pytest.mark.integration`）
   - `test_funasr_transcribe_short_wav()`：对一个很短的 wav（<=10s）至少返回 1 条 utterance

实现步骤：
1. 在 `asr/base.py` 定义 `ASREngine` 抽象：`transcribe(audio_path) -> list[Utterance]`。
2. `asr/mock.py` 实现：
   - 支持 `mock_transcript_path` 配置（或按 wav 文件名映射到 fixtures）
3. `asr/funasr.py` 实现（集成级）：
   - 读取配置：model/vad/punc/spk/device/batch_size
   - 调用 FunASR API 获取分句 + 说话人 + 时间戳
   - 统一输出为 `Utterance` 列表

验证步骤：
- `uv run pytest -q tests/test_asr_mock.py`
- （可选）`uv run pytest -q -m integration`

---

### Task 6/12 - 文本分段器（Segmenter）

目标：把 ASR utterances 按静音间隔/最大时长切成 `Segment`。

依赖：Task 2（模型）、Task 1（配置）。

产出文件：
- `src/audio_journal/segmenter/silence.py`
- `tests/test_segmenter.py`

TDD：
1. `tests/test_segmenter.py`
   - `test_segmenter_splits_on_gap()`：相邻 utterance gap > `min_silence_gap` 时分段
   - `test_segmenter_enforces_max_duration()`：超过 `max_segment_duration` 在最近切点强制切
   - `test_segmenter_drops_too_short()`：小于 `min_segment_duration` 的段被丢弃

实现步骤：
1. `SilenceSegmenter.segment(utterances, source_file) -> list[Segment]`
2. 段 id：MVP 用 `uuid4()` 或 `hash(source_file + start + end)`（保证稳定性更好）
3. 计算 `duration = end_time - start_time`

验证步骤：
- `uv run pytest -q tests/test_segmenter.py`

---

### Task 7/12 - 场景分类器（meeting/business/idea/learning/phone/chat）

目标：对每个 `Segment` 调用 LLM 做场景分类，输出 `ClassifiedSegment`。

依赖：Task 2、Task 3、Task 6。

产出文件：
- `src/audio_journal/classifier/scene.py`
- `prompts/classifier.txt`
- `tests/test_classifier_scene.py`

MVP 范围说明：
- Phase 1 仅做 **单层场景分类**（不做 chat 的价值检测；价值检测是 Phase 2 task 14）。
- 但在代码结构上预留 `value_detector` hook（例如 classifier 内部方法，暂时不调用）。

TDD：
1. `tests/test_classifier_scene.py`
   - `test_classifier_builds_prompt_sample()`：只取前 N 条 utterances 拼成 transcript sample（避免超长输入）
   - `test_classifier_parses_llm_json()`：fake LLM 返回 JSON，断言 scene/confidence 写入 `ClassifiedSegment`
   - `test_classifier_sets_empty_value_tags_in_mvp()`：chat 也返回空 `value_tags`

实现步骤：
1. Prompt 加载：从 `config.paths.prompts` 读取 `classifier.txt`。
2. Transcript 渲染格式：与 prompts 文档一致，例如：`[09:15:03] SPEAKER_00: ...`
3. LLM 调用：`LLMFactory.create(..., stage="classifier")`
4. 解析返回：严格 JSON → `scene/confidence`（reasoning 可丢到 metadata 或日志）

验证步骤：
- `uv run pytest -q tests/test_classifier_scene.py`
- （手动）用 MockASR 的固定 transcript，跑 pipeline 能得到合理 scene

---

### Task 8/12 - 场景分析器（先做 meeting）

目标：实现 Analyzer 抽象与 `MeetingAnalyzer`，把 meeting 段落产出结构化摘要/要点/待办。

依赖：Task 2、Task 3、Task 7。

产出文件：
- `src/audio_journal/analyzer/base.py`
- `src/audio_journal/analyzer/meeting.py`
- `prompts/meeting.txt`
- `tests/test_analyzer_meeting.py`

TDD：
1. `tests/test_analyzer_meeting.py`
   - `test_meeting_analyzer_parses_json_to_result()`：fake LLM 返回 meeting JSON，映射到 `AnalysisResult`
   - `test_meeting_analyzer_puts_decisions_in_metadata()`：decisions/deadlines 等落 `metadata`

实现步骤：
1. `BaseAnalyzer`：负责加载 prompt、渲染模板变量、调用 LLM。
2. `MeetingAnalyzer.analyze(classified_segment)`：
   - 仅接受 `scene == meeting`（否则抛异常或直接跳过）
   - LLM stage=analyzer
   - JSON 映射：
     - `summary` → `AnalysisResult.summary`
     - `key_points` → `AnalysisResult.key_points`
     - `action_items`（结构化）→ `AnalysisResult.metadata["action_items"]`，同时可生成展示用的 `AnalysisResult.action_items`（字符串列表）
     - `participants/topics/decisions` → metadata

验证步骤：
- `uv run pytest -q tests/test_analyzer_meeting.py`

---

### Task 9/12 - 自动归档（本地）+ 索引（供 CLI 查询）

目标：把 `AnalysisResult` 写入本地归档目录，生成 Markdown 文件，并写入索引，支持后续 `list/show/status`。

依赖：Task 2、Task 8。

产出文件：
- `src/audio_journal/archiver/local.py`
- `src/audio_journal/storage/index.py`
- `tests/test_archiver_local.py`
- `tests/test_storage_index.py`

归档格式建议（MVP 可用）：
- 路径：`data/archive/YYYY-MM-DD/<id>-<scene>-<title>.md`
- 文件内容：YAML front-matter + 摘要/要点/待办/原文转写（与设计文档模板一致即可）
- 索引：
  - 每天一个 JSONL：`data/archive/YYYY-MM-DD/index.jsonl`
  - 每条记录一行（便于追加写、避免全量读写）

TDD：
1. `tests/test_storage_index.py`
   - `test_index_append_and_query_by_date(tmp_path)`：写 2 天数据，按日期过滤返回正确
   - `test_index_query_by_scene(tmp_path)`：scene 过滤
   - `test_index_get_by_id(tmp_path)`：show 用 id 精确定位
2. `tests/test_archiver_local.py`
   - `test_archiver_writes_markdown_and_updates_index(tmp_path)`：归档后存在 md 文件 + index.jsonl 增加一条
   - `test_archiver_sanitizes_title_for_filename(tmp_path)`：标题含空格/符号时文件名安全

实现步骤：
1. `storage/index.py` 定义 `ArchiveEntry`（id/date/scene/title/duration/path/source_file 等）。
2. `LocalArchiver.archive(result, context)`：
   - 生成 `id`：建议 `YYYYMMDD-001`（全局唯一且可读）
   - 生成标题：优先用 topics 或 key_points 的短语；fallback 用 scene + 时间
   - 写 markdown（utf-8）
   - 追加写 index.jsonl

验证步骤：
- `uv run pytest -q tests/test_storage_index.py tests/test_archiver_local.py`
- （手动）检查 `data/archive/.../*.md` 内容可读

---

### Task 10/12 - 文件监听服务（watchdog）

目标：监听 `paths.inbox`，检测新 `*.wav` 文件，等待写入稳定后触发 pipeline。

依赖：Task 1（配置）、Task 11（最终会注入 pipeline）；但可先独立做成"回调式 watcher"，方便单测。

产出文件：
- `src/audio_journal/watcher/file_watcher.py`
- `tests/test_watcher.py`

TDD：
1. `tests/test_watcher.py`
   - `test_wait_stable_returns_when_file_stops_growing(tmp_path)`：分两次写文件，断言稳定检测逻辑正确
   - `test_handler_ignores_non_wav()`：创建 txt 不触发

实现步骤：
1. `FileWatcher`：
   - 初始化 watch_dir/patterns/stable_seconds
   - `start(on_audio_ready: Callable[[Path], None])` 前台阻塞运行
2. `AudioFileHandler`：
   - `on_created` 过滤后缀
   - `_wait_stable(path)`：检查 size/mtime 在 stable_seconds 内不变
   - 调用回调

验证步骤：
- `uv run pytest -q tests/test_watcher.py`
- （手动）运行 `audio-journal start`，在 inbox 放入 wav，观察日志触发

---

### Task 11/12 - Pipeline 编排 + `audio-journal start`（前台）

目标：把 chunker/asr/segmenter/classifier/analyzer/archiver 串起来；并提供 `start` 命令启动 watcher + pipeline。

依赖：Task 4、Task 5、Task 6、Task 7、Task 8、Task 9、Task 10。

产出文件：
- `src/audio_journal/pipeline.py`
- `tests/test_pipeline.py`
- （CLI 挂接可先放在 `src/audio_journal/cli.py`，最终由 Task 12 完整覆盖）

TDD：
1. `tests/test_pipeline.py`
   - `test_pipeline_happy_path_with_fakes(tmp_path)`：
     - FakeChunker 返回 1 chunk
     - FakeASR 返回 utterances
     - Segmenter 返回 2 segments
     - Classifier 返回 meeting
     - Analyzer 返回 2 results
     - Archiver 被调用 2 次并写入 index
   - `test_pipeline_continues_on_single_segment_failure()`（建议）：某个段分析失败只记录错误，不影响其他段（MVP 可先不做，作为增强项）

实现步骤：
1. `Pipeline.__init__(config, components=None)`：支持依赖注入（单测用 fake）。
2. `Pipeline.process(audio_path) -> list[AnalysisResult]`：
   - 创建处理目录（processing/transcripts/analysis）
   - `chunker.split` → 对每个 chunk：asr → segment → classify → analyze
   - meeting analyzer：对非 meeting 场景使用 `PassthroughAnalyzer`（只保留 transcript + scene，不调用 LLM），确保 pipeline 不中断且数据不丢失
   - `archiver.archive_all(results)`
3. 输出日志：按 `cli-interaction.md` 的关键节点打印/记录。

验证步骤：
- `uv run pytest -q tests/test_pipeline.py`
- （手动）执行 `audio-journal process <file.wav>` 确认端到端产出归档

---

### Task 12/12 - 管理 CLI（status/list/show）+ process/start 命令整合

目标：实现最小可用的管理 CLI：
- `process <file.wav>`：手动触发完整 pipeline
- `start`：前台监听目录（调用 watcher）
- `status`：显示服务未必常驻（MVP 不做 daemon），因此 status 重点显示"最近归档/今日统计"
- `list [--date YYYY-MM-DD] [--scene scene]`：读取索引列出条目
- `show <id>`：展示单条详情（含归档路径、摘要、要点、待办、原文）

依赖：Task 1、Task 9、Task 11。

产出文件：
- `src/audio_journal/cli.py`
- `tests/test_cli.py`

TDD：
1. `tests/test_cli.py`（用 `click.testing.CliRunner`）
   - `test_cli_list_filters(tmp_path)`：准备 archive/index.jsonl 数据，运行 `list --scene meeting` 输出包含期望条目
   - `test_cli_show(tmp_path)`：`show <id>` 能打印 summary/key_points
   - `test_cli_process_uses_pipeline(monkeypatch)`：用 fake pipeline，断言被调用

实现步骤：
1. `click.group()`：统一入口 `audio-journal`。
2. `--config` 全局选项：允许指定 config 文件路径（默认 `./config.yaml`）。
3. 输出格式：MVP 用纯文本即可；后续可引入 `rich` 优化（不阻塞 Phase 1）。
4. status 的定义（MVP）：
   - 读取最近 N 天 index
   - 汇总"今日归档数量、场景分布、最近一条归档时间"

验证步骤：
- `uv run pytest -q tests/test_cli.py`
- 手动回归：
  - `audio-journal process path/to.wav`
  - `audio-journal list`
  - `audio-journal show <id>`

---

## 4. 最终集成验收清单（Phase 1 完工时跑一遍）

1. 安装与测试：
   - `uv run pytest -q`
2. 手动处理单文件：
   - 准备一个短 wav（<=2min）
   - `audio-journal process ./data/inbox/sample.wav`
   - 断言：`data/archive/YYYY-MM-DD/` 下出现 md + index.jsonl
3. Watcher 跑通：
   - `audio-journal start`
   - 复制一个 wav 到 `data/inbox/`
   - 断言：自动归档产出，`audio-journal list` 可见

---

## 5. 风险点与提前约定（便于 review）

- ASR/FunASR 依赖重：建议 Phase 1 先用 MockASR 保证工程闭环，真实 FunASR 用 integration 测试逐步接入。
- Chunker 仅支持 WAV：与当前设计一致（监听 `*.wav`），若未来要支持 mp3/m4a，再引入 ffmpeg。
- Analyzer 只做 meeting：其他场景在 Phase 2 扩展；Phase 1 对非 meeting 段落采用「只归档 transcript + scene」策略 — 仍然写入索引和归档文件（包含原始转写和场景标签），但不做深度分析（summary/key_points 等留空或标注"待分析"）。这样不丢数据，后续 reprocess 可补充分析。

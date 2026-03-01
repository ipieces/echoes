# Echoes 优化路线图

> 文档版本：v1.1
> 创建日期：2026-03-01
> 最后更新：2026-03-01
> 基于代码审阅报告生成

## 文档概述

本文档基于 2026-03-01 的代码库全面审阅，列出了 Echoes 项目当前存在的问题、改进建议和优化路线图。

**设计原则**：聚焦核心功能，优先完成音频处理和分析的核心能力，暂不考虑 Web UI、高级搜索等外围功能。

优化项按优先级分为四个等级：

- **P0 - 阻塞问题**：必须立即修复，否则项目无法运行
- **P1 - 高优先级**：Phase 1 MVP 完成的必要条件
- **P2 - 中优先级**：Phase 2 功能增强
- **P3 - 低优先级**：长期优化和改进

---

## 一、当前问题清单

### 🔴 P0 - 阻塞问题

#### 1.1 缺失核心模块 `models/schemas.py`

**问题描述**：
- 代码库中大量引用 `audio_journal.models.schemas`
- `src/audio_journal/models/` 目录不存在
- 所有测试因 `ModuleNotFoundError` 无法运行
- 项目无法启动

**影响范围**：
- 所有测试文件（57个测试）
- CLI 命令
- Pipeline 核心流程

**需要定义的模型**：
```python
# 基础数据模型
- SceneType (Enum): meeting, business, idea, learning, phone, chat
- Speaker (Model): speaker_id, name (optional)
- Utterance (Model): speaker, text, start_time, end_time
- Segment (Model): utterances, start_time, end_time, duration
- ClassifiedSegment (Model): segment, scene_type, confidence

# 分析结果模型
- AnalysisResult (Model): scene_type, summary, key_points, metadata
- MeetingAnalysis (Model): summary, key_points, action_items, decisions
- BusinessAnalysis (Model): summary, commitments, follow_ups, key_asks
- IdeaAnalysis (Model): core_idea, idea_type, related_topics
- LearningAnalysis (Model): knowledge_points, sources, key_takeaways
- PhoneAnalysis (Model): caller_intent, agreed_actions, follow_up
- ChatAnalysis (Model): high_value_topics, key_insights

# 归档模型
- DailyReport (Model): date, segments, total_duration, scene_distribution
- ArchiveEntry (Model): id, date, scene_type, title, file_path, metadata
```

**验收标准**：
- [ ] `src/audio_journal/models/schemas.py` 文件创建
- [ ] 所有模型使用 Pydantic BaseModel
- [ ] 包含完整的类型提示和验证规则
- [ ] 所有测试通过（57/57）
- [ ] CLI 命令可正常运行

---

### ⚠️ P1 - 高优先级（Phase 1 MVP 完成）

#### 1.2 ASR 引擎仅 Mock 实现

**问题描述**：
- 当前仅有 `MockASR`，读取预先转录的 JSON 文件
- 无法处理真实音频文件
- 限制了系统的实际可用性

**优化方案**：

**方案 A：集成 FunASR（推荐）**
- 优势：中文优化、说话人分离、本地部署
- 劣势：模型较大（~2GB）、需要 GPU 加速
- 实施步骤：
  1. 创建 `src/audio_journal/asr/funasr.py`
  2. 实现 `FunASREngine(ASREngine)` 类
  3. 添加模型下载脚本 `scripts/download_funasr_models.py`
  4. 更新配置支持 `asr.engine: funasr`
  5. 添加集成测试

**方案 B：集成 WhisperX**
- 优势：英文效果好、社区活跃
- 劣势：中文效果一般、说话人分离需额外配置
- 实施步骤：类似方案 A

**配置示例**：
```yaml
asr:
  engine: funasr  # 或 whisperx
  model: paraformer-zh  # FunASR 中文模型
  device: mps  # Apple Silicon GPU
  vad_model: fsmn-vad
  punc_model: ct-punc
  spk_model: cam++  # 说话人分离模型
  num_speakers: auto  # 自动检测说话人数量
```

**验收标准**：
- [ ] FunASR 引擎实现并通过单元测试
- [ ] 可处理真实 WAV 文件（16kHz, 16-bit PCM）
- [ ] 说话人分离准确率 > 85%
- [ ] 转录准确率 > 90%（中文）
- [ ] 处理速度 < 实时（1小时音频 < 1小时处理）

#### 1.3 场景分析器不完整

**问题描述**：
- 仅实现 `MeetingAnalyzer`
- 其他5个场景（business, idea, learning, phone, chat）使用 `PassthroughAnalyzer`
- 无法提取场景专属的结构化信息

**优化方案**：

**实施步骤**：
1. 创建 `src/audio_journal/analyzer/business.py` - 商务分析器
2. 创建 `src/audio_journal/analyzer/idea.py` - 想法分析器
3. 创建 `src/audio_journal/analyzer/learning.py` - 学习分析器
4. 创建 `src/audio_journal/analyzer/phone.py` - 电话分析器
5. 创建 `src/audio_journal/analyzer/chat.py` - 闲聊分析器（含价值检测）
6. 更新 `pipeline.py` 中的分析器路由逻辑

**各分析器提取内容**：

| 场景 | 提取字段 | 提示词文件 |
|------|---------|-----------|
| Business | 承诺、后续跟进、关键请求、合作机会 | `prompts/business.txt` |
| Idea | 核心想法、想法类型、相关话题、可行性 | `prompts/idea.txt` |
| Learning | 知识点、来源、关键要点、延伸阅读 | `prompts/learning.txt` |
| Phone | 来电意图、约定行动、后续跟进 | `prompts/phone.txt` |
| Chat | 高价值话题、关键洞察、话题分类 | `prompts/chat.txt` |

**验收标准**：
- [ ] 5个分析器全部实现
- [ ] 每个分析器有对应的单元测试
- [ ] 提取字段符合 Pydantic 模型定义
- [ ] LLM 提示词经过测试优化
- [ ] 集成测试覆盖所有场景

#### 1.4 闲聊场景价值检测

**问题描述**：
- 闲聊场景可能包含高价值信息（投资、技术、市场洞察）
- 当前无法识别和标记这些高价值片段
- 导致重要信息淹没在日常对话中

**优化方案**：

**价值检测逻辑**：
```python
class ChatAnalyzer(BaseAnalyzer):
    async def analyze(self, segment: ClassifiedSegment) -> ChatAnalysis:
        # 1. 提取高价值话题
        high_value_topics = await self._detect_value_topics(segment)

        # 2. 对每个话题评分
        scored_topics = [
            {
                "topic": topic,
                "value_score": self._calculate_value_score(topic),
                "category": self._categorize_topic(topic),
                "key_insights": self._extract_insights(topic)
            }
            for topic in high_value_topics
        ]

        # 3. 过滤低价值话题（score < 0.6）
        filtered = [t for t in scored_topics if t["value_score"] >= 0.6]

        return ChatAnalysis(
            high_value_topics=filtered,
            key_insights=[t["key_insights"] for t in filtered],
            topic_distribution=self._get_distribution(filtered)
        )
```

**价值话题分类**：
- 投资机会（investment）
- 技术趋势（tech_trend）
- 市场洞察（market_insight）
- 商业模式（business_model）
- 人脉资源（network）
- 个人成长（personal_growth）

**验收标准**：
- [ ] 价值检测准确率 > 80%
- [ ] 支持自定义价值话题关键词
- [ ] 价值评分算法可配置
- [ ] 高价值片段在归档中突出显示

---

### 🟡 P2 - 中优先级（Phase 2 功能增强）

#### 2.1 并行处理支持

**问题描述**：
- 音频分块顺序处理，无法利用多核 CPU
- 长录音（4小时）处理时间过长
- ASR 和 LLM 调用可并行化

**优化方案**：

**并行化策略**：
```python
# 当前（顺序）
for chunk in chunks:
    transcript = await asr.transcribe(chunk)
    segments = segmenter.segment(transcript)
    for segment in segments:
        classified = await classifier.classify(segment)
        result = await analyzer.analyze(classified)

# 优化后（并行）
# 1. 并行 ASR 转录
transcripts = await asyncio.gather(*[
    asr.transcribe(chunk) for chunk in chunks
])

# 2. 并行分类
classified_segments = await asyncio.gather(*[
    classifier.classify(seg) for seg in all_segments
])

# 3. 并行分析
results = await asyncio.gather(*[
    analyzer.analyze(seg) for seg in classified_segments
])
```

**配置选项**：
```yaml
processing:
  parallel_chunks: true  # 并行处理分块
  max_workers: 4  # 最大并行数
  parallel_classification: true  # 并行分类
  parallel_analysis: true  # 并行分析
```

**验收标准**：
- [ ] 4小时录音处理时间减少 50%+
- [ ] CPU 利用率提升至 60%+
- [ ] 内存占用可控（< 4GB）
- [ ] 支持配置并行度

#### 2.2 处理缓存和去重

**问题描述**：
- 重复处理相同文件浪费资源
- 无法跳过已处理的文件
- 部分失败后需要重新处理整个文件

**优化方案**：

**缓存策略**：
```python
class ProcessingCache:
    """处理缓存管理器"""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_db = cache_dir / "processing_cache.db"

    def get_file_hash(self, file_path: Path) -> str:
        """计算文件 SHA256 哈希"""
        return hashlib.sha256(file_path.read_bytes()).hexdigest()

    def is_processed(self, file_path: Path) -> bool:
        """检查文件是否已处理"""
        file_hash = self.get_file_hash(file_path)
        return self._cache_exists(file_hash)

    def cache_result(self, file_path: Path, result: ProcessingResult):
        """缓存处理结果"""
        file_hash = self.get_file_hash(file_path)
        self._save_cache(file_hash, result)

    def get_cached_result(self, file_path: Path) -> Optional[ProcessingResult]:
        """获取缓存的处理结果"""
        file_hash = self.get_file_hash(file_path)
        return self._load_cache(file_hash)
```

**配置选项**：
```yaml
cache:
  enabled: true
  cache_dir: ./data/cache
  ttl: 2592000  # 30天过期
  skip_processed: true  # 跳过已处理文件
  force_reprocess: false  # 强制重新处理
```

**验收标准**：
- [ ] 重复文件直接跳过
- [ ] 缓存命中率 > 90%
- [ ] 支持强制重新处理
- [ ] 缓存自动清理过期数据

#### 2.3 错误恢复机制

**问题描述**：
- 组件失败时整个流水线停止
- 无法从中断点恢复
- 错误信息不够详细

**优化方案**：

**错误处理策略**：
```python
class ResilientPipeline(Pipeline):
    """具有错误恢复能力的流水线"""

    async def process(self, audio_file: Path) -> ProcessingResult:
        checkpoint = self._load_checkpoint(audio_file)

        try:
            # 1. 分块（可恢复）
            if checkpoint.stage < Stage.CHUNKING:
                chunks = await self._chunking_with_retry(audio_file)
                self._save_checkpoint(audio_file, Stage.CHUNKING, chunks)

            # 2. ASR（可恢复）
            if checkpoint.stage < Stage.ASR:
                transcripts = await self._asr_with_retry(chunks)
                self._save_checkpoint(audio_file, Stage.ASR, transcripts)

            # 3. 分析（部分失败继续）
            results = []
            for segment in segments:
                try:
                    result = await self._analyze_segment(segment)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Segment analysis failed: {e}")
                    results.append(self._create_fallback_result(segment))

            return ProcessingResult(results=results)

        except Exception as e:
            self._save_error_state(audio_file, e)
            raise
```

**验收标准**：
- [ ] 支持从任意阶段恢复
- [ ] 部分失败不影响整体
- [ ] 详细的错误日志和堆栈
- [ ] 失败重试机制（指数退避）

#### 2.4 说话人名称标注和记忆

**问题描述**：
- ASR 输出的说话人标签为 `speaker_0`, `speaker_1`
- 无法识别具体是谁
- 每次处理都需要重新推断

**优化方案**：

**说话人识别策略**：
```python
class SpeakerManager:
    """说话人管理器"""

    def __init__(self, db_path: Path):
        self.db = SpeakerDatabase(db_path)

    async def identify_speakers(
        self,
        utterances: List[Utterance],
        context: Optional[str] = None
    ) -> List[Utterance]:
        """识别说话人身份"""

        # 1. 提取声纹特征（如果有音频）
        embeddings = self._extract_voice_embeddings(utterances)

        # 2. 匹配已知说话人
        matched = self._match_known_speakers(embeddings)

        # 3. 使用 LLM 推断未知说话人
        for utterance in utterances:
            if utterance.speaker_id not in matched:
                name = await self._infer_speaker_name(
                    utterance,
                    context,
                    nearby_utterances
                )
                if name:
                    self.db.add_speaker(utterance.speaker_id, name, embeddings)

        # 4. 更新说话人标签
        return self._update_speaker_labels(utterances, matched)
```

**配置选项**：
```yaml
speaker:
  enable_identification: true
  voice_embedding_model: resemblyzer  # 声纹提取模型
  similarity_threshold: 0.85  # 声纹匹配阈值
  llm_inference: true  # 使用 LLM 推断名字
  manual_labeling: true  # 支持手动标注
```

**验收标准**：
- [ ] 声纹匹配准确率 > 90%
- [ ] 支持手动标注和修正
- [ ] 说话人数据库持久化
- [ ] 跨文件说话人关联

---

### 🟢 P3 - 低优先级（长期优化）

#### 3.1 多语言支持

**问题描述**：
- 当前系统主要针对中文优化
- 英文、日文等其他语言支持不足
- 多语言混合场景处理能力有限

**优化方案**：

**实施步骤**：
1. 添加语言检测模块（使用 langdetect 或 fasttext）
2. 支持多语言 ASR 模型切换
3. 针对不同语言优化 LLM 提示词
4. 处理多语言混合场景（如中英混合）

**配置示例**：
```yaml
language:
  auto_detect: true  # 自动检测语言
  supported: [zh, en, ja]  # 支持的语言
  default: zh  # 默认语言
  mixed_language_handling: true  # 混合语言处理

asr:
  models:
    zh: paraformer-zh
    en: whisper-large-v3
    ja: whisper-large-v3
```

**验收标准**：
- [ ] 支持中文、英文、日文 3 种语言
- [ ] 语言检测准确率 > 95%
- [ ] 混合语言场景正确处理
- [ ] 不同语言使用对应的 ASR 模型



## 二、实施计划

### Phase 1.5：修复阻塞问题（1周）

**目标**：项目可运行，测试全部通过

| 任务 | 工作量 | 验收标准 |
|------|--------|---------|
| 创建 `models/schemas.py` | 2天 | 57/57 测试通过 |
| 验证所有功能 | 1天 | CLI 命令正常运行 |
| 更新文档 | 0.5天 | README 和文档同步 |

### Phase 2：完成 MVP（4周）

**目标**：真实可用的音频日记系统

| 任务 | 工作量 | 依赖 | 验收标准 |
|------|--------|------|---------|
| 集成 FunASR | 1周 | Phase 1.5 | 转录准确率 > 90% |
| 实现 5 个分析器 | 1.5周 | FunASR | 所有场景有专属分析 |
| 闲聊价值检测 | 0.5周 | Chat 分析器 | 价值检测准确率 > 80% |
| 集成测试 | 1周 | 所有分析器 | 端到端测试通过 |

### Phase 3：功能增强（6周）

**目标**：提升性能和用户体验

| 任务 | 工作量 | 依赖 | 验收标准 |
|------|--------|------|---------|
| 并行处理 | 1周 | Phase 2 | 处理速度提升 50% |
| 处理缓存 | 1周 | - | 缓存命中率 > 90% |
| 错误恢复 | 1周 | - | 支持断点续传 |
| 说话人识别 | 1.5周 | - | 匹配准确率 > 90% |

### Phase 4：长期优化（持续）

**目标**：国际化支持

- 多语言支持（中文、英文、日文）
- 语言自动检测
- 混合语言场景处理

---

## 三、风险评估

### 技术风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| FunASR 性能不达标 | 中 | 高 | 准备 WhisperX 备选方案 |
| LLM API 限流 | 高 | 中 | 实现指数退避和本地缓存 |
| 内存占用过高 | 中 | 中 | 优化分块大小和并行度 |
| 说话人识别不准 | 高 | 低 | 支持手动标注 |

### 资源风险

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| GPU 资源不足 | 中 | 高 | 支持 CPU 模式（降速） |
| 存储空间不足 | 低 | 中 | 自动清理旧缓存 |
| API 费用超预算 | 中 | 中 | 设置每日调用上限 |

---

## 四、成功指标

### Phase 1.5 指标

- [ ] 57/57 测试通过
- [ ] 所有 CLI 命令可运行
- [ ] 文档更新完成

### Phase 2 指标

- [ ] 可处理真实音频文件
- [ ] 转录准确率 > 90%（中文）
- [ ] 所有 6 种场景有专属分析
- [ ] 端到端处理成功率 > 95%

### Phase 3 指标

- [ ] 4小时音频处理时间 < 2小时
- [ ] 内存占用 < 4GB
- [ ] 缓存命中率 > 90%
- [ ] 支持断点续传

### Phase 4 指标

- [ ] 支持中文、英文、日文 3 种语言
- [ ] 语言检测准确率 > 95%
- [ ] 混合语言场景正确处理

---

## 五、附录

### A. 参考资料

- [FunASR 官方文档](https://github.com/alibaba-damo-academy/FunASR)
- [WhisperX 项目](https://github.com/m-bain/whisperX)
- [Pydantic 最佳实践](https://docs.pydantic.dev/latest/)

### B. 相关文档

- `docs/system-design.md` - 系统设计文档
- `docs/implementation-plan.md` - 实施计划
- `docs/asr-setup.md` - ASR 设置指南
- `docs/code-review-r1.md` - 代码审查报告

### C. 变更日志

| 日期 | 版本 | 变更内容 | 作者 |
|------|------|---------|------|
| 2026-03-01 | v1.0 | 初始版本，基于代码审阅报告 | - |
| 2026-03-01 | v1.1 | 聚焦核心功能，删除 Web UI、高级搜索、实时处理等外围功能 | - |

---

**文档结束**

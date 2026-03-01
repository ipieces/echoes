# Audio Journal P1 优先级实施计划

> 基于 `docs/optimization-roadmap-0301.md` P1 高优先级问题
> 目标：完成 Phase 1 MVP，使系统真实可用

## 背景

当前状态：
- ✅ P0 已解决：`schemas.py` 存在，51/51 测试通过
- ❌ P1 阻塞：ASR 仅 Mock，无法处理真实音频
- ❌ P1 阻塞：5 个场景分析器缺失（business/idea/learning/phone/chat）
- ❌ P1 阻塞：闲聊场景无价值检测

## 实施优先级

按依赖关系和影响范围排序：

### 任务 1：集成 FunASR 引擎（最高优先级）

**为什么优先**：
- 阻塞所有真实音频处理
- 其他功能依赖真实转写结果
- 独立模块，不影响现有代码

**实施步骤**：

1. **创建 FunASR 引擎实现** (`src/audio_journal/asr/funasr.py`)
   ```python
   class FunASREngine(ASREngine):
       """FunASR 引擎实现（中文优化 + 说话人分离）"""
       
       def __init__(self, config: ASRConfig):
           # 加载模型：paraformer-zh (ASR) + cam++ (说话人分离)
           pass
       
       def transcribe(self, audio_path: str) -> list[Utterance]:
           # 1. VAD 检测语音段
           # 2. ASR 转写
           # 3. 说话人分离
           # 4. 标点恢复
           # 5. 返回 Utterance 列表
           pass
   ```

2. **添加模型下载脚本** (`scripts/download_funasr_models.py`)
   - 下载 4 个模型：paraformer-zh, fsmn-vad, ct-punc, cam++
   - 总大小约 2GB
   - 保存到 `models/` 目录

3. **更新配置支持** (`config.yaml`)
   ```yaml
   asr:
     engine: funasr  # 新增选项
     model: paraformer-zh
     device: mps  # Apple Silicon GPU
     vad_model: fsmn-vad
     punc_model: ct-punc
     spk_model: cam++
   ```

4. **添加集成测试** (`tests/test_asr_funasr.py`)
   - 测试真实 WAV 文件转写
   - 验证说话人分离
   - 检查转写准确率

**验收标准**：
- [ ] FunASR 引擎可加载模型
- [ ] 可处理真实 WAV 文件（16kHz, 16-bit PCM）
- [ ] 说话人分离输出 SPEAKER_00, SPEAKER_01 等标签
- [ ] 转写准确率 > 90%（中文测试音频）
- [ ] 处理速度 < 实时（1小时音频 < 1小时处理）
- [ ] 集成测试通过

**预估工作量**：3-4 天

---

### 任务 2：实现 5 个场景分析器（次高优先级）

**为什么次优先**：
- 依赖 FunASR 提供真实转写
- 但可以先用 Mock ASR 开发和测试
- 独立模块，可并行开发

**实施步骤**：

#### 2.1 Business 分析器 (`src/audio_journal/analyzer/business.py`)

**提取字段**：
- 承诺（commitments）：对方承诺的事项
- 后续跟进（follow_ups）：需要跟进的行动
- 关键请求（key_asks）：我方的关键请求
- 合作机会（opportunities）：潜在合作机会

**Prompt 设计** (`prompts/business.txt`)：
```
你是商务对话分析专家。分析以下商务拜访/洽谈的转写文本，提取：

1. 承诺：对方明确承诺的事项（时间、资源、支持等）
2. 后续跟进：需要跟进的行动（发送资料、安排会议等）
3. 关键请求：我方提出的关键请求
4. 合作机会：讨论中提到的潜在合作机会

输出 JSON：
{
  "summary": "简短摘要",
  "commitments": ["承诺1", "承诺2"],
  "follow_ups": ["跟进1", "跟进2"],
  "key_asks": ["请求1", "请求2"],
  "opportunities": ["机会1", "机会2"],
  "key_points": ["要点1", "要点2"]
}
```

#### 2.2 Idea 分析器 (`src/audio_journal/analyzer/idea.py`)

**提取字段**：
- 核心想法（core_idea）：主要想法描述
- 想法类型（idea_type）：灵感/反思/计划
- 相关话题（related_topics）：关联的话题标签
- 可行性（feasibility）：初步可行性评估

**Prompt 设计** (`prompts/idea.txt`)：
```
你是创意分析专家。分析以下自言自语/思考的转写文本，提取：

1. 核心想法：主要想法的简洁描述
2. 想法类型：灵感（新点子）、反思（对过往的思考）、计划（未来行动）
3. 相关话题：关联的话题标签（技术、产品、商业等）
4. 可行性：初步评估（高/中/低/未知）

输出 JSON：
{
  "core_idea": "核心想法描述",
  "idea_type": "inspiration|reflection|plan",
  "related_topics": ["话题1", "话题2"],
  "feasibility": "high|medium|low|unknown",
  "key_points": ["要点1", "要点2"]
}
```

#### 2.3 Learning 分析器 (`src/audio_journal/analyzer/learning.py`)

**提取字段**：
- 知识点（knowledge_points）：学到的知识点
- 来源（sources）：学习来源（视频、课程、文章等）
- 关键要点（key_takeaways）：关键收获
- 延伸阅读（further_reading）：值得深入的方向

#### 2.4 Phone 分析器 (`src/audio_journal/analyzer/phone.py`)

**提取字段**：
- 来电意图（caller_intent）：对方打电话的目的
- 约定行动（agreed_actions）：双方约定的行动
- 后续跟进（follow_up）：需要跟进的事项

#### 2.5 Chat 分析器 + 价值检测 (`src/audio_journal/analyzer/chat.py`)

**提取字段**：
- 高价值话题（high_value_topics）：包含价值信息的话题
- 话题分类（topic_categories）：投资/技术/市场/人脉等
- 关键洞察（key_insights）：有价值的洞察
- 价值评分（value_score）：0-1 分数

**价值检测逻辑**：
```python
class ChatAnalyzer(BaseAnalyzer):
    async def analyze(self, segment: ClassifiedSegment) -> AnalysisResult:
        # 1. 提取所有话题
        topics = await self._extract_topics(segment)
        
        # 2. 价值检测
        high_value = []
        for topic in topics:
            score = await self._calculate_value_score(topic)
            if score >= 0.6:  # 阈值可配置
                high_value.append({
                    "topic": topic,
                    "score": score,
                    "category": self._categorize(topic),
                    "insights": self._extract_insights(topic)
                })
        
        # 3. 生成结果
        return AnalysisResult(
            segment_id=segment.id,
            scene=SceneType.CHAT,
            summary=self._generate_summary(high_value),
            key_points=[t["insights"] for t in high_value],
            topics=[t["topic"] for t in high_value],
            value_level="high" if high_value else "normal",
            metadata={
                "high_value_topics": high_value,
                "value_distribution": self._get_distribution(high_value)
            }
        )
```

**价值话题分类**：
- investment：投资机会、融资信息
- tech_trend：技术趋势、新技术
- market_insight：市场洞察、行业分析
- business_model：商业模式、盈利策略
- network：人脉资源、关键人物
- personal_growth：个人成长、职业发展

**验收标准**：
- [ ] 5 个分析器全部实现
- [ ] 每个分析器有单元测试
- [ ] Prompt 经过测试优化
- [ ] Chat 分析器价值检测准确率 > 80%
- [ ] 集成测试覆盖所有场景

**预估工作量**：5-6 天（每个分析器 1 天）

---

### 任务 3：更新 Pipeline 路由逻辑

**当前问题**：
```python
# pipeline.py 当前逻辑
for seg in classified:
    if seg.scene == SceneType.MEETING:
        res = await self.meeting_analyzer.analyze(seg)
    else:
        res = await self.passthrough_analyzer.analyze(seg)  # ❌ 其他场景用 Passthrough
```

**修改为**：
```python
# pipeline.py 新逻辑
class Pipeline:
    def __init__(self, config: AppConfig, ...):
        # 初始化所有分析器
        self.analyzers = {
            SceneType.MEETING: MeetingAnalyzer(llm, ...),
            SceneType.BUSINESS: BusinessAnalyzer(llm, ...),
            SceneType.IDEA: IdeaAnalyzer(llm, ...),
            SceneType.LEARNING: LearningAnalyzer(llm, ...),
            SceneType.PHONE: PhoneAnalyzer(llm, ...),
            SceneType.CHAT: ChatAnalyzer(llm, ...),
        }
    
    async def process(self, audio_path: str | Path) -> list[AnalysisResult]:
        # ...
        for seg in classified:
            analyzer = self.analyzers[seg.scene]
            res = await analyzer.analyze(seg)
            all_results.append(res)
```

**验收标准**：
- [ ] Pipeline 支持所有 6 种场景
- [ ] 路由逻辑清晰，易于扩展
- [ ] 端到端测试通过

**预估工作量**：0.5 天

---

## 实施时间线

| 任务 | 工作量 | 开始日期 | 完成日期 | 依赖 |
|------|--------|---------|---------|------|
| 任务 1：FunASR 集成 | 3-4 天 | Day 1 | Day 4 | 无 |
| 任务 2.1：Business 分析器 | 1 天 | Day 2 | Day 2 | 无（可用 Mock ASR） |
| 任务 2.2：Idea 分析器 | 1 天 | Day 3 | Day 3 | 无 |
| 任务 2.3：Learning 分析器 | 1 天 | Day 4 | Day 4 | 无 |
| 任务 2.4：Phone 分析器 | 1 天 | Day 5 | Day 5 | 无 |
| 任务 2.5：Chat 分析器 | 2 天 | Day 6 | Day 7 | 无 |
| 任务 3：Pipeline 路由 | 0.5 天 | Day 8 | Day 8 | 任务 2 |
| 集成测试 | 1 天 | Day 9 | Day 9 | 任务 1, 2, 3 |

**总工作量**：9-10 天

## 并行开发策略

由于任务 1（FunASR）和任务 2（分析器）相对独立，可以并行开发：

- **Sub-agent 1**：负责 FunASR 集成（任务 1）
- **Sub-agent 2**：负责 5 个分析器实现（任务 2）
- **主 agent**：负责 Pipeline 路由更新和集成测试（任务 3）

这样可以将总时间压缩到 **5-6 天**。

## 验收标准（Phase 1 MVP 完成）

- [ ] 可处理真实音频文件（WAV 格式）
- [ ] 转写准确率 > 90%（中文）
- [ ] 所有 6 种场景有专属分析器
- [ ] Chat 场景价值检测准确率 > 80%
- [ ] 端到端测试通过
- [ ] 所有单元测试通过（预计 70+ 测试）

## 风险和缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| FunASR 性能不达标 | 中 | 高 | 准备 WhisperX 备选方案 |
| LLM API 限流 | 高 | 中 | 实现指数退避和本地缓存 |
| Prompt 效果不佳 | 中 | 中 | 迭代优化，准备多版本 Prompt |
| 说话人分离不准 | 高 | 低 | 文档说明限制，后续支持手动标注 |

## 下一步行动

1. **立即启动**：创建两个 sub-agent
   - Sub-agent 1：FunASR 集成
   - Sub-agent 2：5 个分析器实现
2. **监督 review**：主 agent 监督进度，review 代码
3. **集成测试**：所有模块完成后进行端到端测试
4. **文档更新**：更新 README 和使用文档

---

**计划结束**

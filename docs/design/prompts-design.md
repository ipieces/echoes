# Audio Journal — Prompt 设计

所有 LLM 调用的 prompt 模板。分为两类：分类 prompt 和分析 prompt。

---

## 1. 场景分类 Prompt (`prompts/classifier.txt`)

```
你是一个音频内容场景分类器。根据以下 ASR 转写文本片段，判断它属于哪个场景。

## 场景定义

1. meeting — 工作会议
   特征：多人讨论工作事项、项目进展、技术方案、任务分配
   说话人：通常 3+ 人，语气较正式

2. business — 商务拜访
   特征：客户/供应商/渠道/合作方的正式或半正式交流，涉及合作、报价、需求
   说话人：通常 2-4 人，有明确的甲乙方关系

3. idea — 灵感/自言自语
   特征：个人思考、灵感记录、自我对话、计划梳理
   说话人：通常 1 人（用户自己）

4. learning — 学习/观看视频
   特征：听课、看视频、阅读讨论，内容偏知识性
   说话人：可能 1 人（视频音频）或 2+ 人（讨论）

5. phone — 电话通话
   特征：电话交流，通常只有两个说话人，可能有电话铃声/提示音
   说话人：通常 2 人

6. chat — 朋友闲聊
   特征：非工作的社交对话，轻松随意
   说话人：2+ 人，语气轻松

## 判断依据

- 说话人数量和关系
- 对话语气（正式/随意）
- 内容主题（工作/社交/学习）
- 对话结构（有议程 vs 自由发散）

## 输入

以下是一段 ASR 转写文本（包含说话人标签和时间戳）：

---
{{transcript}}
---

## 输出

严格输出 JSON，不要输出其他内容：

{"scene": "<scene_type>", "confidence": 0.0-1.0, "reasoning": "一句话理由"}
```

---

## 2. 价值检测 Prompt (`prompts/value_detector.txt`)

闲聊场景专用，检测是否包含高价值内容。

```
以下是一段被分类为"朋友闲聊"的对话转写。请检测其中是否包含以下高价值话题：

## 高价值话题类型

- 投融资信息：融资轮次、投资金额、估值、上市计划、投资方
- 技术讨论：架构设计、算法、新技术、工具评测、技术趋势
- 市场解读：行业趋势、竞争分析、市场机会、政策影响
- 人脉信息：关键人物、组织变动、合作机会、人事调整
- 商业洞察：商业模式、盈利策略、成本分析、创业经验

## 输入

---
{{transcript}}
---

## 输出

严格输出 JSON：

{
  "has_value": true/false,
  "value_tags": ["投融资信息", "技术讨论"],
  "valuable_segments": [
    {
      "topic": "投融资信息",
      "summary": "朋友公司完成B轮融资，估值约2亿",
      "start_time": "12:35:00",
      "end_time": "12:38:00"
    }
  ]
}

如果纯闲聊无价值内容，输出：
{"has_value": false, "value_tags": [], "valuable_segments": []}
```

---

## 3. 工作会议分析 Prompt (`prompts/meeting.txt`)

```
你是一个专业的会议记录分析师。请分析以下工作会议的 ASR 转写文本，提取结构化信息。

## 输入

会议时间：{{start_time}} - {{end_time}}
说话人：{{speakers}}

---
{{transcript}}
---

## 提取要求

1. 摘要：用 2-3 句话概括会议核心内容
2. 关键要点：列出 3-7 个最重要的讨论点或结论
3. 决策：明确记录会议中做出的决策
4. 待办事项：提取所有 action items，标注责任人和截止时间（如有）
5. 参与者：列出参与讨论的人（用说话人标签）
6. 话题标签：3-5 个关键词标签

## 注意事项

- ASR 转写可能有错别字，请根据上下文理解原意
- 如果责任人不明确，标注为 [待确认]
- 截止时间如果只是口头提及（如"下周"），转换为具体日期

## 输出

严格输出 JSON：

{
  "summary": "会议摘要",
  "key_points": ["要点1", "要点2"],
  "decisions": ["决策1", "决策2"],
  "action_items": [
    {"task": "任务描述", "owner": "SPEAKER_XX", "deadline": "YYYY-MM-DD 或 null"}
  ],
  "participants": ["SPEAKER_00", "SPEAKER_01"],
  "topics": ["标签1", "标签2"]
}
```

---

## 4. 商务拜访分析 Prompt (`prompts/business.txt`)

```
你是一个商务沟通分析师。请分析以下商务拜访/交流的 ASR 转写文本。

## 输入

时间：{{start_time}} - {{end_time}}
说话人：{{speakers}}

---
{{transcript}}
---

## 提取要求

1. 摘要：概括此次商务交流的核心内容
2. 对方诉求：对方（客户/供应商/合作方）的核心需求或关注点
3. 我方承诺：我方做出的承诺或表态
4. 关键信息：涉及的金额、时间节点、技术要求等具体信息
5. 跟进事项：需要后续跟进的事项，标注责任方
6. 关系评估：合作意向强度（高/中/低）

## 输出

严格输出 JSON：

{
  "summary": "交流摘要",
  "counterpart_needs": ["对方诉求1", "对方诉求2"],
  "our_commitments": ["承诺1", "承诺2"],
  "key_info": {"金额": "xxx", "时间节点": "xxx", "技术要求": "xxx"},
  "follow_ups": [
    {"task": "跟进事项", "owner": "我方/对方", "deadline": "YYYY-MM-DD 或 null"}
  ],
  "cooperation_level": "high/medium/low",
  "participants": ["SPEAKER_00", "SPEAKER_01"],
  "topics": ["标签1", "标签2"]
}
```

---

## 5. 灵感/自言自语分析 Prompt (`prompts/idea.txt`)

```
你是一个个人思维整理助手。请分析以下个人独白/自言自语的 ASR 转写文本，提炼核心想法。

## 输入

时间：{{start_time}} - {{end_time}}

---
{{transcript}}
---

## 提取要求

1. 核心想法：提炼 1-3 个主要想法或灵感
2. 想法类型：判断属于哪种类型
   - inspiration：突发灵感、创意
   - reflection：反思、复盘
   - planning：计划、安排
   - problem：问题思考、困惑
3. 关联主题：这些想法可能关联到哪些项目或领域
4. 可行动项：如果想法中包含可执行的下一步，提取出来

## 输出

严格输出 JSON：

{
  "summary": "思考摘要",
  "ideas": [
    {"content": "想法描述", "type": "inspiration/reflection/planning/problem"}
  ],
  "related_topics": ["关联主题1", "关联主题2"],
  "action_items": ["可行动项1"],
  "topics": ["标签1", "标签2"]
}
```

---

## 6. 学习/视频分析 Prompt (`prompts/learning.txt`)

```
你是一个学习笔记整理助手。请分析以下学习/观看视频场景的 ASR 转写文本，提取知识要点。

## 输入

时间：{{start_time}} - {{end_time}}
说话人：{{speakers}}

---
{{transcript}}
---

## 提取要求

1. 主题：学习内容的主题
2. 来源类型：视频/课程/播客/阅读讨论
3. 知识要点：提取 3-7 个核心知识点
4. 个人笔记：如果用户有发表评论或感想，单独提取
5. 延伸阅读：如果提到了推荐的资源、书籍、工具，记录下来

## 输出

严格输出 JSON：

{
  "summary": "学习内容摘要",
  "source_type": "video/course/podcast/discussion",
  "key_learnings": ["知识点1", "知识点2"],
  "personal_notes": ["个人感想1"],
  "references": ["推荐资源1"],
  "topics": ["标签1", "标签2"]
}
```

---

## 7. 电话通话分析 Prompt (`prompts/phone.txt`)

```
你是一个电话沟通记录分析师。请分析以下电话通话的 ASR 转写文本。

## 输入

时间：{{start_time}} - {{end_time}}
说话人：{{speakers}}（通常 SPEAKER_00 为用户本人）

---
{{transcript}}
---

## 提取要求

1. 摘要：通话核心内容
2. 对方身份：根据对话内容推断对方身份/角色
3. 通话目的：谁发起的、为什么打这个电话
4. 关键信息：涉及的具体信息（时间、地点、金额等）
5. 约定事项：双方达成的约定
6. 跟进事项：需要后续跟进的事项

## 输出

严格输出 JSON：

{
  "summary": "通话摘要",
  "caller_identity": "对方身份推断",
  "call_purpose": "通话目的",
  "key_info": {"具体信息": "值"},
  "agreements": ["约定1", "约定2"],
  "follow_ups": [
    {"task": "跟进事项", "owner": "我/对方", "deadline": "YYYY-MM-DD 或 null"}
  ],
  "topics": ["标签1", "标签2"]
}
```

---

## 8. 闲聊分析 Prompt (`prompts/chat.txt`)

```
你是一个社交对话分析助手。请分析以下朋友闲聊的 ASR 转写文本。

注意：此段对话已被价值检测器标记为包含高价值内容。

## 输入

时间：{{start_time}} - {{end_time}}
说话人：{{speakers}}
检测到的价值标签：{{value_tags}}

---
{{transcript}}
---

## 提取要求

1. 摘要：简要概括聊天内容
2. 高价值片段提取：针对每个价值标签，提取相关的具体信息
3. 人物信息：如果提到了有价值的人物信息，记录下来
4. 可行动项：如果聊天中产生了值得跟进的事项

## 输出

严格输出 JSON：

{
  "summary": "聊天摘要",
  "valuable_insights": [
    {
      "tag": "投融资信息",
      "content": "具体信息描述",
      "source_speaker": "SPEAKER_XX"
    }
  ],
  "people_mentioned": [
    {"name": "人名", "context": "相关背景"}
  ],
  "action_items": ["可跟进事项"],
  "topics": ["标签1", "标签2"]
}
```

---

## 9. Prompt 模板变量

所有 prompt 中使用的模板变量：

| 变量 | 说明 | 示例 |
|------|------|------|
| `{{transcript}}` | ASR 转写文本（含时间戳和说话人） | `[09:15:03] SPEAKER_00: 好，开始吧...` |
| `{{start_time}}` | 片段开始时间 | `09:15` |
| `{{end_time}}` | 片段结束时间 | `10:32` |
| `{{speakers}}` | 说话人列表 | `SPEAKER_00(你), SPEAKER_01, SPEAKER_02` |
| `{{value_tags}}` | 价值检测标签（仅闲聊场景） | `投融资信息, 市场解读` |

## 10. Prompt 优化策略

全自动模式下，prompt 质量直接决定归档质量。优化路径：

1. **基线建立**：先用当前 prompt 跑一批数据，人工抽检评估质量
2. **错误分类收集**：记录分类错误的案例，补充到 prompt 的 few-shot 示例中
3. **分析质量评估**：对比 AI 摘要和原文，标注遗漏/错误的要点
4. **迭代更新**：修改 prompt 后用 `audio-journal reprocess` 重新处理历史数据验证效果
5. **参数调优**：调整 temperature、max_tokens 等参数

# FunASR 时间戳修复总结

## 问题描述

在运行 batch 处理时发现：
- ASR 转写完成，但生成 0 个归档项
- 根本原因：FunASR 未返回时间戳信息，导致所有 utterances 的时间戳都是 0.0
- 这导致后续的场景分段、分类、分析和归档流程无法正常工作

## 根本原因分析

1. **旧模型不支持时间戳**
   - 原配置使用：`damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch`
   - 该模型不支持输出时间戳信息

2. **缺少关键参数**
   - FunASR 在使用 VAD 模式时，必须设置 `sentence_timestamp=True` 才能获取句子级时间戳
   - 原代码未设置此参数

3. **缺少字段解析逻辑**
   - 时间戳数据存储在 `sentence_info` 字段，而非 `timestamp` 字段
   - 原代码未实现 `sentence_info` 的解析逻辑

## 解决方案

### 1. 更换支持时间戳的模型

**文件**: `config.zai.yaml`

```yaml
asr:
  model: iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch
  # 旧模型: damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch
```

**说明**: 只有 `iic/` 命名空间的模型支持时间戳输出

### 2. 添加 sentence_timestamp 参数

**文件**: `src/audio_journal/asr/funasr.py`

**位置 1** (第 111 行):
```python
result = self._model.generate(
    input=audio_path,
    batch_size=self.config.batch_size,
    language=self.config.language,
    sentence_timestamp=True,  # 启用句子级时间戳
)
```

**位置 2** (第 137 行，降级重试时):
```python
result = self._model.generate(
    input=audio_path,
    batch_size=self.config.batch_size,
    language=self.config.language,
    sentence_timestamp=True,  # 启用句子级时间戳
)
```

### 3. 实现 sentence_info 解析逻辑

**文件**: `src/audio_journal/asr/funasr.py`

**位置**: 第 196-215 行

```python
# 如果有 sentence_info，使用它来构建 utterances
if sentence_info:
    print(f"\n✅ 找到 sentence_info，使用句子级时间戳")
    for sent in sentence_info:
        if isinstance(sent, dict):
            sent_text = sent.get("text", "")
            sent_start = sent.get("start", 0) / 1000.0  # 转换为秒
            sent_end = sent.get("end", 0) / 1000.0
            sent_speaker = sent.get("spk", "SPEAKER_00")

            if sent_text.strip():
                utterances.append(
                    Utterance(
                        speaker=Speaker(id=sent_speaker),
                        text=sent_text,
                        start_time=sent_start,
                        end_time=sent_end,
                    )
                )
    continue  # 跳过后续的 timestamp 处理
```

**说明**:
- `sentence_info` 是一个列表，每个元素包含 `text`, `start`, `end`, `spk` 字段
- 时间单位是毫秒，需要除以 1000 转换为秒

### 4. 修正 z.ai 配置

**文件**: `src/audio_journal/llm/openai_compat.py`

```python
# 修正 base_url
"zhipuai": "https://api.z.ai/api/paas/v4",  # 原: https://open.bigmodel.cn/api/paas/v4
```

## 验证结果

### 测试脚本输出

```
测试文件: example/asr_example.wav

=== 结果 ===
生成了 5 条 utterances

前 3 条:
1. [0.43s - 2.21s] SPEAKER_00: 正是因为存在绝对正义，...
2. [2.27s - 4.54s] SPEAKER_00: 所以我们接受现实的相对正义，...
3. [5.29s - 7.49s] SPEAKER_00: 但是不要因为现实的相对正义，...

✅ 成功！时间戳正确解析！
```

### FunASR 返回数据结构

**不带 sentence_timestamp**:
```python
['key', 'text', 'timestamp']
```

**带 sentence_timestamp=True**:
```python
['key', 'text', 'timestamp', 'sentence_info']
```

**sentence_info 示例**:
```json
{
  "text": "正是因为存在绝对正义，",
  "start": 430,
  "end": 2210,
  "timestamp": [[430, 670], [670, 810], ...]
}
```

## 修改的文件清单

1. `config.zai.yaml` - 更新 ASR 模型配置
2. `src/audio_journal/asr/funasr.py` - 添加时间戳支持和解析逻辑
3. `src/audio_journal/llm/openai_compat.py` - 修正 z.ai base URL

## 下一步

运行完整的 batch 处理来验证端到端流程：

```bash
source .venv/bin/activate
export ZHIPUAI_API_KEY="your_api_key"
python -m audio_journal.cli --config config.zai.yaml batch
```

预期结果：
- ASR 转写生成带时间戳的 utterances
- 场景分段器正确分段
- 分类器和分析器正常工作
- 生成归档文件（不再是 "0 archived"）

## 技术要点

1. **模型选择**: 只有 `iic/` 命名空间的 FunASR 模型支持时间戳
2. **参数设置**: VAD 模式下必须设置 `sentence_timestamp=True`
3. **数据结构**: 时间戳在 `sentence_info` 字段，不在 `timestamp` 字段
4. **时间单位**: `sentence_info` 中的时间是毫秒，需要转换为秒
5. **降级处理**: 说话人分离失败时自动重新加载模型（不含 spk_model）

## 参考资料

- FunASR 源码: `funasr/auto/auto_model.py` (第 621-626 行)
- 模型下载: ModelScope Hub
- 配置文件: `config.zai.yaml`

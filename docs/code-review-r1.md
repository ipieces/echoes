# Audio Journal — Code Review (Round 1)

## 总体评价

代码结构清晰，模块划分合理，30 个测试全部通过。TDD 执行到位，每个模块都有对应测试。以下是需要改进的问题，按优先级排列。

---

## 🔴 必须修复

### 1. watcher/file_watcher.py 缺少 `__init__.py`
`src/audio_journal/watcher/` 目录没有 `__init__.py`，虽然测试通过了（可能因为 Python 3.11 的 namespace packages），但为了一致性应该补上。

### 2. Pipeline.process() 中 segment 的 source_file 不准确
```python
segments = self.segmenter.segment(utterances, source_file=str(chunk.path.name))
```
这里 `source_file` 用的是 chunk 文件名（如 `chunk_001.wav`），但归档时应该用原始音频文件名。建议传入原始文件名，或在 segment 中同时记录 chunk 和原始文件信息。

### 3. archiver/local.py 的 `_slugify` 对中文标题处理不当
```python
_slug_re = re.compile(r"[^a-zA-Z0-9_-]+")
```
这个正则会把所有中文字符替换掉，导致中文标题的文件名变成空的或只剩连字符。应该保留中文字符：
```python
_slug_re = re.compile(r"[^\w-]+", re.UNICODE)
```

### 4. CLI `start` 命令中 asyncio.run 在回调中使用有隐患
```python
def _on_audio_ready(p: Path) -> None:
    asyncio.run(pipe.process(p))
```
每次文件触发都创建新的 event loop，如果处理时间长且有新文件进来，watchdog 的回调线程会阻塞。MVP 可以接受，但应该加个注释标注这是已知限制。

---

## 🟡 建议改进

### 5. config.yaml 中 `asr.engine` 默认值应改为 `mock`
当前默认是 `funasr`，但 FunASR 未实现。用户首次运行会直接报错。MVP 阶段建议默认 `mock`，或者在 Pipeline 初始化时给出更友好的错误提示。

### 6. LLM Factory 的 claude fallback 逻辑应该打日志
```python
if stage and provider != cfg.provider:
    return LLMFactory.create(cfg, stage=None)
```
静默 fallback 会让用户困惑为什么配置了 claude 但实际用的是 deepseek。应该加 `logging.warning`。

### 7. Chunker 的 `_silence_rms_threshold` 应该可配置
当前硬编码为 200.0，不同录音设备的底噪差异很大。建议加到 ChunkerConfig 中。

### 8. 归档 Markdown 的 front-matter 应该用 YAML 格式
当前手动拼接字符串，如果 title 包含冒号等特殊字符会破坏 YAML 格式。建议用 `yaml.dump` 生成 front-matter。

### 9. 测试覆盖缺口
- 没有测试 Pipeline 处理多个 chunk 的场景
- 没有测试 archiver 处理中文标题的边界情况
- CLI 的 `status` 命令没有测试

### 10. prompts/ 目录缺少其他场景的 prompt 文件
设计文档中有 6 个场景 + 1 个 value_detector 的 prompt，但只创建了 classifier.txt 和 meeting.txt。虽然 Phase 1 只用这两个，但建议把其他 prompt 文件也创建好（内容从 prompts-design.md 复制），方便 Phase 2 直接使用。

---

## 🟢 做得好的地方

- 依赖注入设计：Pipeline 支持注入所有组件，测试友好
- MockASR 策略：避免了对真实模型的依赖
- JSONL 索引设计：简单高效，支持按日期/场景查询
- PassthroughAnalyzer：非 meeting 场景不丢数据
- 配置的 resolve_paths：相对路径自动解析为绝对路径
- parse_json_strict：对 LLM 输出的容错处理合理

---

## 修复优先级

1. 补 `watcher/__init__.py`
2. 修复中文 slugify
3. Pipeline source_file 传递
4. config.yaml 默认 asr.engine
5. LLM fallback 加日志
6. Chunker threshold 可配置
7. front-matter 用 yaml.dump
8. 补充测试覆盖
9. 创建剩余 prompt 文件

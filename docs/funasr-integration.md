# FunASR 集成指南

## 概述

Audio Journal 现已支持 FunASR 引擎，可以处理真实音频文件。FunASR 提供：

- **ASR (paraformer-zh)**: 中文语音识别
- **VAD (fsmn-vad)**: 语音活动检测
- **标点恢复 (ct-punc)**: 自动添加标点符号
- **说话人分离 (cam++)**: 识别不同说话人

## 安装

### 1. 安装依赖

```bash
uv add funasr modelscope
```

或使用 pip:

```bash
pip install funasr modelscope
```

### 2. 下载模型

运行模型下载脚本：

```bash
python scripts/download_funasr_models.py
```

这将下载以下模型到 `./models` 目录：

- `paraformer-zh` (857 MB) - ASR 模型
- `fsmn-vad` - VAD 模型
- `ct-punc` - 标点恢复模型
- `cam++` - 说话人分离模型

下载单个模型：

```bash
python scripts/download_funasr_models.py --model paraformer-zh
```

## 配置

在 `config.yaml` 中配置 FunASR：

```yaml
asr:
  engine: funasr  # 从 mock 改为 funasr
  model: paraformer-zh
  vad_model: fsmn-vad
  punc_model: ct-punc
  spk_model: cam++
  device: mps  # mps (Apple Silicon) | cpu | cuda
  batch_size: 4
  language: zh
  model_dir: ./models
```

### 设备选择

- **mps**: Apple Silicon GPU (M1/M2/M3) - 推荐用于 Mac
- **cpu**: CPU 模式 - 兼容性最好，但速度较慢
- **cuda**: NVIDIA GPU - 需要 CUDA 环境

## 使用

### 命令行

处理单个音频文件：

```bash
audio-journal process recording.wav
```

批处理（日级）：

```bash
audio-journal batch 2026-03-01
```

### Python API

```python
from pathlib import Path
from audio_journal.config import load_config
from audio_journal.pipeline import Pipeline

# 加载配置
config = load_config("config.yaml")

# 创建 Pipeline
pipeline = Pipeline(config)

# 处理音频
results = await pipeline.process("recording.wav")

# 查看结果
for result in results:
    print(f"场景: {result.scene}")
    print(f"摘要: {result.summary}")
    print(f"关键点: {result.key_points}")
```

## 性能

### 预期性能指标

- **转写准确率**: > 90% (中文清晰语音)
- **处理速度**: < 实时 (1小时音频 < 1小时处理)
- **说话人分离**: 支持多说话人场景

### 优化建议

1. **使用 Apple Silicon GPU (mps)**:
   - 在 M1/M2/M3 Mac 上显著提升速度
   - 配置 `device: mps`

2. **调整 batch_size**:
   - 增大 batch_size 可提升吞吐量
   - 但会增加内存占用
   - 推荐值: 4-8

3. **音频预处理**:
   - 使用 16kHz 采样率
   - 16-bit PCM 格式
   - 单声道音频

## 测试

运行 FunASR 测试：

```bash
pytest tests/test_asr_funasr.py -v
```

运行所有测试：

```bash
pytest
```

## 故障排除

### 模型加载失败

**错误**: `模型文件缺失`

**解决**:
```bash
python scripts/download_funasr_models.py
```

### 内存不足

**错误**: `CUDA out of memory` 或系统内存不足

**解决**:
1. 减小 `batch_size`
2. 使用 CPU 模式: `device: cpu`
3. 处理较短的音频片段

### 转写结果为空

**可能原因**:
1. 音频文件损坏或格式不支持
2. 音频质量太差（噪音过大）
3. 语言不匹配（模型是中文，但音频是英文）

**解决**:
1. 检查音频文件是否可以正常播放
2. 使用 `ffmpeg` 转换音频格式:
   ```bash
   ffmpeg -i input.mp3 -ar 16000 -ac 1 output.wav
   ```
3. 确认音频语言与配置匹配

## 与 MockASR 对比

| 特性 | MockASR | FunASR |
|------|---------|--------|
| 真实转写 | ❌ | ✅ |
| 说话人分离 | ✅ (预设) | ✅ (真实) |
| 处理速度 | 极快 | 接近实时 |
| 准确率 | N/A | > 90% |
| 依赖 | 无 | funasr, modelscope |
| 模型大小 | 0 | ~1.5 GB |
| 适用场景 | 测试/开发 | 生产环境 |

## 下一步

- [ ] 支持英文模型 (paraformer-en)
- [ ] 实时流式转写
- [ ] 自定义热词
- [ ] 语言模型微调

## 参考

- [FunASR GitHub](https://github.com/modelscope/FunASR)
- [ModelScope 模型库](https://www.modelscope.cn/models?page=1&tasks=auto-speech-recognition)
- [Audio Journal 文档](docs/)

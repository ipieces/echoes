# FunASR 模型下载与本地缓存说明

本项目后续会把 ASR 引擎从 `MockASR` 切换为真实的 FunASR。为了避免首次运行时在线拉取模型导致卡顿/失败，建议先把模型下载到项目本地的 `models/` 目录。

补充：FunASR 的预训练模型通常发布在 ModelScope（主渠道）与 HuggingFace（镜像/同步）。本项目的下载脚本使用 ModelScope 的公开 API（无需安装 `modelscope` Python 包）完成下载与校验。

## 1. 下载脚本

项目已提供下载脚本：

- `scripts/download_models.py`

该脚本会下载以下模型（与 `config.yaml` 默认配置一致）：

- `paraformer-zh`（ASR）
- `fsmn-vad`（VAD）
- `ct-punc`（标点）
- `cam++`（说话人识别 / 说话人确认）

实现特点：

- 断点续传：每个文件用 `.part` 临时文件 + HTTP Range 续传
- 进度显示：优先使用 `tqdm`（可选），否则输出文本进度
- 避免重复下载：已存在且校验通过会跳过
- 完整性校验：使用 ModelScope API 提供的 `SHA256` 对每个文件校验

## 2. 如何运行

在项目根目录执行：

```bash
uv run python scripts/download_models.py
```

只下载某一个模型：

```bash
uv run python scripts/download_models.py --only paraformer-zh
```

强制重新下载（忽略已完成标记）：

```bash
uv run python scripts/download_models.py --force
```

提示：`cam++` 目录名包含 `+`，在 shell 里如果需要手动操作，建议加引号，例如：`"models/cam++"`。

## 3. 依赖说明（可选）

脚本使用项目现有依赖 `httpx` 完成下载。

如需更好的进度条显示，建议额外安装：

```bash
uv pip install tqdm
```

## 4. 模型文件存储位置

下载完成后，模型会存放在：

- `models/paraformer-zh/`
- `models/fsmn-vad/`
- `models/ct-punc/`
- `models/cam++/`

每个模型目录内会生成一个完成标记文件：

- `models/<model>/.download_complete.json`

该文件记录了：模型来源（ModelScope）、revision、文件列表、大小和 SHA256，用于后续跳过重复下载与校验。

## 5. 磁盘空间需求（估算）

不同 revision 可能略有变化，这里给一个经验值：

- `paraformer-zh` 约 0.9 GB（主模型文件较大）
- `fsmn-vad` / `ct-punc` / `cam++` 通常为几十 MB 量级

建议预留至少 2 GB 可用空间，避免下载中途磁盘不足。

## 6. 如何验证下载成功

最简单的验证方式：重复运行下载脚本。

- 如果输出类似“已存在且校验通过，跳过。”，说明模型文件齐全且 SHA256 校验通过。

也可以检查标记文件是否存在：

- `models/<model>/.download_complete.json`

如需进一步确认，可对照标记文件中的 `files` 列表，检查每个文件的 `size` / `sha256`。

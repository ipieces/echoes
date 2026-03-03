#!/usr/bin/env python3
"""下载 FunASR 模型到本地。

使用 ModelScope 下载以下模型：
1. paraformer-zh (ASR) - 857 MB
2. fsmn-vad (VAD)
3. ct-punc (标点恢复)
4. cam++ (说话人分离)
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def download_model(model_id: str, cache_dir: Path) -> str:
    """从 ModelScope 下载模型。

    Args:
        model_id: ModelScope 模型 ID (如 damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch)
        cache_dir: 缓存目录

    Returns:
        实际下载的模型路径
    """
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError as e:
        raise RuntimeError(
            "ModelScope 未安装。请运行: pip install modelscope"
        ) from e

    logger.info(f"下载模型: {model_id}")
    logger.info(f"  缓存目录: {cache_dir}")

    # 下载模型（ModelScope 会自动使用 model_id 作为子目录）
    model_path = snapshot_download(
        model_id=model_id,
        cache_dir=str(cache_dir),
    )

    logger.info(f"  下载完成: {model_path}")
    return model_path


def main() -> None:
    parser = argparse.ArgumentParser(description="下载 FunASR 模型")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./models"),
        help="模型输出目录（默认: ./models）",
    )
    parser.add_argument(
        "--model",
        type=str,
        choices=["paraformer-zh", "fsmn-vad", "ct-punc", "cam++", "all"],
        default="all",
        help="要下载的模型（默认: all）",
    )

    args = parser.parse_args()

    # 模型 ID 映射
    model_ids = {
        "paraformer-zh": "damo/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-pytorch",
        "fsmn-vad": "damo/speech_fsmn_vad_zh-cn-16k-common-pytorch",
        "ct-punc": "damo/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",
        "cam++": "damo/speech_campplus_sv_zh-cn_16k-common",
    }

    # 确定要下载的模型
    if args.model == "all":
        models_to_download = model_ids.items()
    else:
        models_to_download = [(args.model, model_ids[args.model])]

    # 创建输出目录
    args.output_dir.mkdir(parents=True, exist_ok=True)

    # 下载模型
    for model_name, model_id in models_to_download:
        # 检查模型是否已存在（使用完整的模型 ID 路径）
        model_path = args.output_dir / model_id
        if model_path.exists():
            logger.info(f"模型已存在，跳过: {model_name} ({model_path})")
            continue

        try:
            actual_path = download_model(model_id, args.output_dir)
            logger.info(f"✅ {model_name} 下载成功: {actual_path}")
        except Exception as e:
            logger.error(f"❌ 下载失败: {model_name} - {e}")
            continue

    logger.info("\n🎉 所有模型下载完成")


if __name__ == "__main__":
    main()

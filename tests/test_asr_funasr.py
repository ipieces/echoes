from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from audio_journal.asr.funasr import FunASREngine
from audio_journal.config import ASRConfig


@pytest.fixture
def asr_config() -> ASRConfig:
    """创建测试用 ASR 配置。"""
    return ASRConfig(
        engine="funasr",
        model="paraformer-zh",
        vad_model="fsmn-vad",
        punc_model="ct-punc",
        spk_model="cam++",
        device="cpu",  # 测试时使用 CPU
        batch_size=1,
        language="zh",
    )


@pytest.fixture
def model_dir(tmp_path: Path) -> Path:
    """创建临时模型目录。"""
    model_dir = tmp_path / "models"
    model_dir.mkdir()

    # 创建模型目录结构
    for model_name in ["paraformer-zh", "fsmn-vad", "ct-punc", "cam++"]:
        (model_dir / model_name).mkdir()
        # 创建一个空的配置文件，模拟模型存在
        (model_dir / model_name / "config.yaml").write_text("# dummy config")

    return model_dir


def test_funasr_engine_init_missing_models(asr_config: ASRConfig, tmp_path: Path) -> None:
    """测试模型文件缺失时的错误处理。"""
    with pytest.raises(RuntimeError, match="模型文件缺失"):
        FunASREngine(asr_config, model_dir=tmp_path / "nonexistent")


@patch("funasr.AutoModel")
def test_funasr_engine_loads_model(
    mock_automodel: MagicMock, asr_config: ASRConfig, model_dir: Path
) -> None:
    """测试 FunASR 引擎加载模型。"""
    # 创建 mock 模型
    mock_model = MagicMock()
    mock_automodel.return_value = mock_model

    # 初始化引擎
    engine = FunASREngine(asr_config, model_dir=model_dir)

    # 验证 AutoModel 被调用
    mock_automodel.assert_called_once()
    call_kwargs = mock_automodel.call_args.kwargs

    assert str(model_dir / "paraformer-zh") in call_kwargs["model"]
    assert str(model_dir / "fsmn-vad") in call_kwargs["vad_model"]
    assert str(model_dir / "ct-punc") in call_kwargs["punc_model"]
    assert str(model_dir / "cam++") in call_kwargs["spk_model"]
    assert call_kwargs["device"] == "cpu"


@patch("funasr.AutoModel")
def test_funasr_transcribe_with_speaker(
    mock_automodel: MagicMock, asr_config: ASRConfig, model_dir: Path
) -> None:
    """测试带说话人分离的转写。"""
    # 创建 mock 模型
    mock_model = MagicMock()
    mock_automodel.return_value = mock_model

    # 模拟 FunASR 返回结果
    mock_model.generate.return_value = [
        {
            "text": "你好，我是张三。很高兴见到你。",
            "timestamp": [
                [0, 500, "你好"],
                [500, 1000, "，"],
                [1000, 1500, "我是"],
                [1500, 2000, "张三"],
                [2000, 2500, "。"],
                [2500, 3000, "很"],
                [3000, 3500, "高兴"],
                [3500, 4000, "见到"],
                [4000, 4500, "你"],
                [4500, 5000, "。"],
            ],
            "speaker": [
                [0, 2500, 0],  # SPEAKER_00: 你好，我是张三。
                [2500, 5000, 1],  # SPEAKER_01: 很高兴见到你。
            ],
        }
    ]

    # 初始化引擎并转写
    engine = FunASREngine(asr_config, model_dir=model_dir)
    utterances = engine.transcribe("test.wav")

    # 验证结果
    assert len(utterances) == 2

    # 第一个说话人
    assert utterances[0].speaker.id == "SPEAKER_00"
    assert "你好" in utterances[0].text
    assert "张三" in utterances[0].text
    assert utterances[0].start_time == 0.0
    assert utterances[0].end_time == 2.5

    # 第二个说话人
    assert utterances[1].speaker.id == "SPEAKER_01"
    assert "很高兴" in utterances[1].text
    assert utterances[1].start_time == 2.5
    assert utterances[1].end_time == 5.0


@patch("funasr.AutoModel")
def test_funasr_transcribe_without_speaker(
    mock_automodel: MagicMock, asr_config: ASRConfig, model_dir: Path
) -> None:
    """测试不带说话人分离的转写。"""
    # 创建 mock 模型
    mock_model = MagicMock()
    mock_automodel.return_value = mock_model

    # 模拟 FunASR 返回结果（无说话人信息）
    mock_model.generate.return_value = [
        {
            "text": "今天天气不错。",
            "timestamp": [
                [0, 500, "今天"],
                [500, 1000, "天气"],
                [1000, 1500, "不错"],
                [1500, 2000, "。"],
            ],
            "speaker": [],  # 无说话人信息
        }
    ]

    # 初始化引擎并转写
    engine = FunASREngine(asr_config, model_dir=model_dir)
    utterances = engine.transcribe("test.wav")

    # 验证结果
    assert len(utterances) == 1
    assert utterances[0].speaker.id == "SPEAKER_00"
    assert utterances[0].text == "今天天气不错。"
    assert utterances[0].start_time == 0.0
    assert utterances[0].end_time == 2.0


@patch("funasr.AutoModel")
def test_funasr_transcribe_empty_result(
    mock_automodel: MagicMock, asr_config: ASRConfig, model_dir: Path
) -> None:
    """测试空结果处理。"""
    # 创建 mock 模型
    mock_model = MagicMock()
    mock_automodel.return_value = mock_model

    # 模拟 FunASR 返回空结果
    mock_model.generate.return_value = []

    # 初始化引擎并转写
    engine = FunASREngine(asr_config, model_dir=model_dir)
    utterances = engine.transcribe("test.wav")

    # 验证结果
    assert len(utterances) == 0


@pytest.mark.skipif(
    not os.path.exists("./models/paraformer-zh"),
    reason="需要真实模型文件（运行 scripts/download_funasr_models.py）",
)
def test_funasr_real_model_integration(asr_config: ASRConfig, tmp_path: Path) -> None:
    """集成测试：使用真实模型转写音频。

    注意：此测试需要：
    1. 下载模型（scripts/download_funasr_models.py）
    2. 准备测试音频文件
    """
    # 检查测试音频是否存在
    test_audio = Path("test_data/sample.wav")
    if not test_audio.exists():
        pytest.skip("测试音频文件不存在: test_data/sample.wav")

    # 使用真实模型
    engine = FunASREngine(asr_config, model_dir=Path("./models"))
    utterances = engine.transcribe(str(test_audio))

    # 基本验证
    assert len(utterances) > 0
    for utt in utterances:
        assert utt.speaker.id.startswith("SPEAKER_")
        assert len(utt.text) > 0
        assert utt.end_time >= utt.start_time

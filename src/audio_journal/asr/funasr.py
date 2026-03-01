from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from audio_journal.asr.base import ASREngine
from audio_journal.config import ASRConfig
from audio_journal.models.schemas import Speaker, Utterance

logger = logging.getLogger(__name__)


class FunASREngine(ASREngine):
    """FunASR 引擎实现。

    支持：
    - ASR (paraformer-zh)
    - VAD (fsmn-vad)
    - 标点恢复 (ct-punc)
    - 说话人分离 (cam++)
    """

    def __init__(self, config: ASRConfig, model_dir: str | Path = "./models") -> None:
        self.config = config
        self.model_dir = Path(model_dir)
        self._model: Any = None
        self._load_model()

    def _load_model(self) -> None:
        """加载 FunASR 模型。"""
        try:
            from funasr import AutoModel
        except ImportError as e:
            raise RuntimeError(
                "FunASR 未安装。请运行: pip install funasr modelscope"
            ) from e

        # 检查模型目录
        asr_model_path = self.model_dir / self.config.model
        vad_model_path = self.model_dir / self.config.vad_model
        punc_model_path = self.model_dir / self.config.punc_model
        spk_model_path = self.model_dir / self.config.spk_model

        missing_models = []
        for name, path in [
            ("ASR", asr_model_path),
            ("VAD", vad_model_path),
            ("标点", punc_model_path),
            ("说话人分离", spk_model_path),
        ]:
            if not path.exists():
                missing_models.append(f"{name} ({path})")

        if missing_models:
            raise RuntimeError(
                f"模型文件缺失:\n" + "\n".join(f"  - {m}" for m in missing_models)
            )

        logger.info(f"加载 FunASR 模型: {self.config.model}")
        logger.info(f"  - ASR: {asr_model_path}")
        logger.info(f"  - VAD: {vad_model_path}")
        logger.info(f"  - 标点: {punc_model_path}")
        logger.info(f"  - 说话人分离: {spk_model_path}")
        logger.info(f"  - 设备: {self.config.device}")

        # 加载模型
        # FunASR AutoModel 支持同时加载多个模型
        self._model = AutoModel(
            model=str(asr_model_path),
            vad_model=str(vad_model_path),
            punc_model=str(punc_model_path),
            spk_model=str(spk_model_path),
            device=self.config.device,
        )

        logger.info("FunASR 模型加载完成")

    def transcribe(self, audio_path: str) -> list[Utterance]:
        """转写音频文件。

        Args:
            audio_path: 音频文件路径（支持 WAV, MP3 等格式）

        Returns:
            带时间戳与说话人标签的 utterances
        """
        if self._model is None:
            raise RuntimeError("FunASR 模型未加载")

        logger.info(f"转写音频: {audio_path}")

        # FunASR generate 方法
        # 返回格式: list[dict] with keys: text, timestamp, speaker
        result = self._model.generate(
            input=audio_path,
            batch_size=self.config.batch_size,
            language=self.config.language,
        )

        # 解析结果
        utterances: list[Utterance] = []

        # FunASR 返回格式可能是嵌套的，需要处理
        if not result:
            logger.warning(f"FunASR 返回空结果: {audio_path}")
            return utterances

        # result 通常是 list[dict]，每个 dict 包含一个音频文件的结果
        for item in result:
            if not isinstance(item, dict):
                logger.warning(f"FunASR 返回格式异常: {type(item)}")
                continue

            # 提取文本和时间戳
            text = item.get("text", "")
            timestamp = item.get("timestamp", [])
            speaker = item.get("speaker", [])

            # timestamp 格式: [[start_ms, end_ms, word], ...]
            # speaker 格式: [[start_ms, end_ms, speaker_id], ...]

            # 如果有说话人分离结果，按说话人分段
            if speaker:
                utterances.extend(self._parse_with_speaker(text, timestamp, speaker))
            else:
                # 没有说话人分离，按时间戳分段
                utterances.extend(self._parse_without_speaker(text, timestamp))

        logger.info(f"转写完成: {len(utterances)} 条 utterances")
        return utterances

    def _parse_with_speaker(
        self, text: str, timestamp: list, speaker: list
    ) -> list[Utterance]:
        """解析带说话人分离的结果。"""
        utterances: list[Utterance] = []

        # speaker 格式: [[start_ms, end_ms, speaker_id], ...]
        for spk_seg in speaker:
            if len(spk_seg) < 3:
                continue

            start_ms, end_ms, speaker_id = spk_seg[0], spk_seg[1], spk_seg[2]
            start_time = start_ms / 1000.0
            end_time = end_ms / 1000.0

            # 提取该说话人时间段内的文本
            segment_text = self._extract_text_in_range(
                text, timestamp, start_ms, end_ms
            )

            if segment_text.strip():
                utterances.append(
                    Utterance(
                        speaker=Speaker(id=f"SPEAKER_{speaker_id:02d}"),
                        text=segment_text,
                        start_time=start_time,
                        end_time=end_time,
                    )
                )

        return utterances

    def _parse_without_speaker(self, text: str, timestamp: list) -> list[Utterance]:
        """解析不带说话人分离的结果。"""
        utterances: list[Utterance] = []

        # 没有说话人信息，使用默认说话人
        if timestamp:
            # timestamp 格式: [[start_ms, end_ms, word], ...]
            # 按句子分段（通过标点符号）
            sentences = self._split_by_punctuation(text, timestamp)
            for sent_text, start_ms, end_ms in sentences:
                utterances.append(
                    Utterance(
                        speaker=Speaker(id="SPEAKER_00"),
                        text=sent_text,
                        start_time=start_ms / 1000.0,
                        end_time=end_ms / 1000.0,
                    )
                )
        else:
            # 没有时间戳，整段作为一个 utterance
            utterances.append(
                Utterance(
                    speaker=Speaker(id="SPEAKER_00"),
                    text=text,
                    start_time=0.0,
                    end_time=0.0,
                )
            )

        return utterances

    def _extract_text_in_range(
        self, text: str, timestamp: list, start_ms: float, end_ms: float
    ) -> str:
        """提取指定时间范围内的文本。"""
        words = []
        for ts in timestamp:
            if len(ts) < 3:
                continue
            word_start, word_end, word = ts[0], ts[1], ts[2]
            # 判断词是否在时间范围内
            if word_start >= start_ms and word_end <= end_ms:
                words.append(word)

        return "".join(words)

    def _split_by_punctuation(
        self, text: str, timestamp: list
    ) -> list[tuple[str, float, float]]:
        """按标点符号分句。"""
        sentences: list[tuple[str, float, float]] = []
        current_words = []
        current_start = None
        current_end = None

        punctuation = {"。", "！", "？", "；", ".", "!", "?", ";"}

        for ts in timestamp:
            if len(ts) < 3:
                continue
            word_start, word_end, word = ts[0], ts[1], ts[2]

            if current_start is None:
                current_start = word_start

            current_words.append(word)
            current_end = word_end

            # 遇到标点符号，分句
            if word in punctuation:
                sentences.append(
                    ("".join(current_words), current_start, current_end)
                )
                current_words = []
                current_start = None
                current_end = None

        # 处理最后一句（没有标点符号结尾）
        if current_words and current_start is not None and current_end is not None:
            sentences.append(("".join(current_words), current_start, current_end))

        return sentences

from __future__ import annotations

from abc import ABC, abstractmethod

from audio_journal.models.schemas import Utterance


class ASREngine(ABC):
    """ASR 引擎抽象。"""

    @abstractmethod
    def transcribe(self, audio_path: str) -> list[Utterance]:
        """转写音频文件，返回带时间戳与说话人标签的 utterances。"""

        raise NotImplementedError

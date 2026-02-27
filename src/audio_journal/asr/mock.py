from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from audio_journal.asr.base import ASREngine
from audio_journal.models.schemas import Speaker, Utterance


class MockASREngine(ASREngine):
    """用于单测/本地跑通的 Mock ASR。

    从 JSON fixture 读取 utterances，避免依赖真实模型。
    """

    def __init__(self, fixture_path: str | Path) -> None:
        self.fixture_path = Path(fixture_path)

    def transcribe(self, audio_path: str) -> list[Utterance]:
        raw = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("mock ASR fixture 必须是 list")

        utterances: list[Utterance] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("mock ASR fixture 每条必须是 dict")
            speaker_id = str(item.get("speaker", "SPEAKER_00"))
            utterances.append(
                Utterance(
                    speaker=Speaker(id=speaker_id),
                    text=str(item.get("text", "")),
                    start_time=float(item.get("start_time", 0.0)),
                    end_time=float(item.get("end_time", 0.0)),
                )
            )

        return utterances

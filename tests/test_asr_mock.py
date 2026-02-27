from __future__ import annotations

import json
from pathlib import Path

from audio_journal.asr.mock import MockASREngine


def test_mock_asr_loads_fixture(tmp_path: Path) -> None:
    fixture = tmp_path / "asr.json"
    fixture.write_text(
        json.dumps(
            [
                {
                    "speaker": "SPEAKER_00",
                    "text": "你好",
                    "start_time": 0.0,
                    "end_time": 1.2,
                },
                {
                    "speaker": "SPEAKER_01",
                    "text": "嗯",
                    "start_time": 1.5,
                    "end_time": 2.0,
                },
            ]
        ),
        encoding="utf-8",
    )

    engine = MockASREngine(fixture)
    utterances = engine.transcribe("dummy.wav")

    assert len(utterances) == 2
    assert utterances[0].speaker.id == "SPEAKER_00"
    assert utterances[0].text == "你好"
    assert utterances[1].speaker.id == "SPEAKER_01"

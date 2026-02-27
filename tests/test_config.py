from __future__ import annotations

from pathlib import Path

from audio_journal.config import load_config


def test_load_config_defaults_and_paths(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
paths:
  inbox: ./inbox
  processing: ./processing
  transcripts: ./transcripts
  analysis: ./analysis
  prompts: ./prompts
chunker:
  max_chunk_duration: 14400
""".lstrip(),
        encoding="utf-8",
    )

    cfg = load_config(cfg_path)

    assert cfg.chunker.max_chunk_duration == 14400
    assert cfg.paths.inbox == (tmp_path / "inbox").resolve()
    assert cfg.paths.processing == (tmp_path / "processing").resolve()
    assert cfg.paths.transcripts == (tmp_path / "transcripts").resolve()
    assert cfg.paths.analysis == (tmp_path / "analysis").resolve()
    assert cfg.paths.prompts == (tmp_path / "prompts").resolve()


def test_load_config_env_api_key(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TEST_LLM_API_KEY", "secret")

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        """
llm:
  provider: deepseek
  model: deepseek-chat
  api_key_env: TEST_LLM_API_KEY
""".lstrip(),
        encoding="utf-8",
    )

    cfg = load_config(cfg_path)
    assert cfg.llm.api_key_env == "TEST_LLM_API_KEY"
    assert cfg.llm.get_api_key() == "secret"

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import BaseModel, Field


class ASRConfig(BaseModel):
    # Phase 1 MVP 默认使用 mock，避免用户首次运行直接踩到未实现的引擎。
    engine: str = "mock"
    model: str = "paraformer-zh"
    vad_model: str = "fsmn-vad"
    punc_model: str = "ct-punc"
    spk_model: str = "cam++"
    device: str = "mps"
    batch_size: int = 4
    language: str = "zh"
    model_dir: Path = Path("./models")  # 模型存储目录


class ChunkerConfig(BaseModel):
    min_silence_gap: float = 30.0
    # 16-bit PCM 的 RMS 静音判定阈值；不同设备底噪不同，建议按需调整。
    silence_rms_threshold: float = 200.0
    # 注意：默认值必须与设计文档一致（4 小时）
    max_chunk_duration: float = 14400.0
    min_chunk_duration: float = 60.0
    parallel: bool = True
    max_workers: int = 4


class SegmenterConfig(BaseModel):
    min_silence_gap: float = 30.0
    max_segment_duration: float = 1800.0
    min_segment_duration: float = 10.0


class LLMStageOverride(BaseModel):
    provider: str
    model: str
    api_key_env: Optional[str] = None
    base_url: Optional[str] = None


class LLMOverrides(BaseModel):
    classifier: Optional[LLMStageOverride] = None
    analyzer: Optional[LLMStageOverride] = None


class LLMConfig(BaseModel):
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    api_key_env: str = "DEEPSEEK_API_KEY"
    base_url: Optional[str] = None
    temperature: float = 0.3
    max_tokens: int = 4096
    overrides: LLMOverrides = Field(default_factory=LLMOverrides)

    def get_api_key(self) -> str:
        """从环境变量读取 API key。

        为了避免明文密钥落盘，配置文件只保存 env var 名称。
        """

        key = os.getenv(self.api_key_env, "")
        if not key:
            raise RuntimeError(f"缺少环境变量: {self.api_key_env}")
        return key


class ArchiveLocalConfig(BaseModel):
    base_dir: Path = Path("./data/archive")


class ArchiveObsidianConfig(BaseModel):
    vault_path: Path = Path("/path/to/obsidian/vault")
    base_dir: str = "AudioJournal"


class ArchiveConfig(BaseModel):
    default_target: Literal["local", "obsidian"] = "local"
    local: ArchiveLocalConfig = Field(default_factory=ArchiveLocalConfig)
    obsidian: ArchiveObsidianConfig = Field(default_factory=ArchiveObsidianConfig)


class PathsConfig(BaseModel):
    inbox: Path = Path("./data/inbox")
    processing: Path = Path("./data/processing")
    transcripts: Path = Path("./data/transcripts")
    analysis: Path = Path("./data/analysis")
    prompts: Path = Path("./prompts")


class WatcherConfig(BaseModel):
    watch_dir: Path = Path("./data/inbox")
    patterns: list[str] = Field(default_factory=lambda: ["*.wav"])
    stable_seconds: int = 5
    daemon: bool = False


class BatchConfig(BaseModel):
    """日级批处理配置。"""

    processed_dir: Path = Path("./data/processed")


class MergerConfig(BaseModel):
    """Segment 合并器配置。"""

    enabled: bool = True
    max_gap_between_segments: float = 600.0  # 秒，最大允许间隔（10分钟）
    max_merged_duration: float = 7200.0  # 秒，合并后最长时长（2小时）
    mergeable_scenes: list[str] = Field(
        default_factory=lambda: ["meeting", "learning", "business"]
    )


class AppConfig(BaseModel):
    asr: ASRConfig = Field(default_factory=ASRConfig)
    chunker: ChunkerConfig = Field(default_factory=ChunkerConfig)
    segmenter: SegmenterConfig = Field(default_factory=SegmenterConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    scenes: list[str] = Field(
        default_factory=lambda: ["meeting", "business", "idea", "learning", "phone", "chat"]
    )

    archive: ArchiveConfig = Field(default_factory=ArchiveConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    watcher: WatcherConfig = Field(default_factory=WatcherConfig)
    batch: BatchConfig = Field(default_factory=BatchConfig)
    merger: MergerConfig = Field(default_factory=MergerConfig)

    def resolve_paths(self, base_dir: Path) -> "AppConfig":
        """将配置中的相对路径基于 base_dir 展开为绝对路径。"""

        def _abs(p: Path) -> Path:
            return p if p.is_absolute() else (base_dir / p).resolve()

        data: dict[str, Any] = self.model_dump()

        # asr
        data["asr"]["model_dir"] = _abs(Path(data["asr"]["model_dir"]))

        # paths
        data["paths"]["inbox"] = _abs(Path(data["paths"]["inbox"]))
        data["paths"]["processing"] = _abs(Path(data["paths"]["processing"]))
        data["paths"]["transcripts"] = _abs(Path(data["paths"]["transcripts"]))
        data["paths"]["analysis"] = _abs(Path(data["paths"]["analysis"]))
        data["paths"]["prompts"] = _abs(Path(data["paths"]["prompts"]))

        # watcher
        data["watcher"]["watch_dir"] = _abs(Path(data["watcher"]["watch_dir"]))

        # archive
        data["archive"]["local"]["base_dir"] = _abs(Path(data["archive"]["local"]["base_dir"]))
        data["archive"]["obsidian"]["vault_path"] = _abs(
            Path(data["archive"]["obsidian"]["vault_path"])
        )

        # batch
        data["batch"]["processed_dir"] = _abs(Path(data["batch"]["processed_dir"]))

        return AppConfig.model_validate(data)


def load_config(path: str | Path) -> AppConfig:
    """从 YAML 加载配置并做基础路径解析。"""

    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if raw is None:
        raw = {}
    cfg = AppConfig.model_validate(raw)
    return cfg.resolve_paths(config_path.parent)

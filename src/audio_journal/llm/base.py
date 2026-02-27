from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Optional

from audio_journal.config import LLMConfig, LLMStageOverride


class LLMError(RuntimeError):
    """LLM 调用或解析失败。"""


class LLMProvider(ABC):
    """统一的 LLM Provider 抽象。"""

    @abstractmethod
    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        raise NotImplementedError


def parse_json_strict(text: str) -> dict[str, Any]:
    """尽量严格地从返回文本中解析 JSON。

    允许最小容错：
    - 去掉 ```json fenced code block
    - 从第一个 "{" 到最后一个 "}" 截取
    """

    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json\n", "", 1).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMError(f"无法解析 JSON: {text!r}")
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError as e:
            raise LLMError(f"无法解析 JSON: {text!r}") from e


class LLMFactory:
    """根据配置创建 Provider，并支持按 stage 覆盖。"""

    @staticmethod
    def _effective_config(cfg: LLMConfig, stage: Optional[str]) -> LLMStageOverride | LLMConfig:
        if not stage:
            return cfg

        override = getattr(cfg.overrides, stage, None)
        if override is None:
            return cfg
        return override

    @staticmethod
    def create(cfg: LLMConfig, stage: Optional[str] = None) -> LLMProvider:
        from audio_journal.llm.openai_compat import OpenAICompatibleProvider

        eff = LLMFactory._effective_config(cfg, stage)
        provider = getattr(eff, "provider")
        model = getattr(eff, "model")
        api_key_env = getattr(eff, "api_key_env", None) or cfg.api_key_env
        base_url = getattr(eff, "base_url", None) or cfg.base_url

        # Phase 1 MVP: 优先支持 OpenAI-compatible 协议（OpenAI/DeepSeek/z.ai）。
        if provider in {"openai", "deepseek", "zai"}:
            return OpenAICompatibleProvider(
                provider=provider,
                model=model,
                api_key_env=api_key_env,
                base_url=base_url,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
            )

        # 兼容默认配置里的 claude：如果没实现，回退到主配置 provider。
        if stage and provider != cfg.provider:
            logging.warning(
                "LLM provider '%s'（stage=%s）未实现，已回退到默认 provider '%s'",
                provider,
                stage,
                cfg.provider,
            )
            return LLMFactory.create(cfg, stage=None)

        raise NotImplementedError(f"未支持的 LLM provider: {provider}")

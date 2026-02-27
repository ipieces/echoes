from __future__ import annotations

import os
from typing import Optional

import httpx

from audio_journal.llm.base import LLMError, LLMProvider


def _default_base_url(provider: str) -> str:
    if provider == "openai":
        return "https://api.openai.com/v1"
    if provider == "deepseek":
        return "https://api.deepseek.com/v1"
    if provider == "zai":
        # 智谱 AI（z.ai / BigModel）为 OpenAI Chat Completions 兼容形态，但 base_url 不是 /v1。
        return "https://open.bigmodel.cn/api/paas/v4"
    raise NotImplementedError(provider)


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI Chat Completions 兼容协议。

    可用于 OpenAI 或 DeepSeek 这类兼容接口。
    """

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key_env: str,
        base_url: Optional[str],
        temperature: float,
        max_tokens: int,
        timeout_s: float = 30.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.api_key_env = api_key_env
        self.base_url = (base_url or _default_base_url(provider)).rstrip("/")
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout_s = timeout_s

    def _get_api_key(self) -> str:
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise LLMError(f"缺少环境变量: {self.api_key_env}")
        return key

    async def complete(self, prompt: str, system: str = "", json_mode: bool = False) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._get_api_key()}",
            "Content-Type": "application/json",
        }

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        timeout = httpx.Timeout(self.timeout_s)
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)

        if resp.status_code >= 400:
            raise LLMError(f"LLM 请求失败: {resp.status_code} {resp.text}")

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"]
        except Exception as e:  # noqa: BLE001
            raise LLMError(f"LLM 响应格式异常: {data!r}") from e

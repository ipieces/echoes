from __future__ import annotations

import httpx
import respx

from audio_journal.config import LLMConfig, LLMOverrides, LLMStageOverride
from audio_journal.llm.base import LLMFactory, parse_json_strict
from audio_journal.llm.openai_compat import OpenAICompatibleProvider


@respx.mock
async def test_llm_complete_returns_text(monkeypatch) -> None:
    monkeypatch.setenv("TEST_API_KEY", "k")

    provider = OpenAICompatibleProvider(
        provider="openai",
        model="gpt-test",
        api_key_env="TEST_API_KEY",
        base_url="https://example.com/v1",
        temperature=0.0,
        max_tokens=16,
    )

    route = respx.post("https://example.com/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "hello"}}]},
        )
    )

    out = await provider.complete("hi")
    assert route.called
    assert out == "hello"


def test_llm_complete_json_mode_and_parse() -> None:
    payload = '{"scene":"meeting","confidence":0.9,"reasoning":"ok"}'
    data = parse_json_strict(payload)
    assert data["scene"] == "meeting"
    assert data["confidence"] == 0.9


def test_llm_factory_overrides_and_fallback() -> None:
    cfg = LLMConfig(
        provider="deepseek",
        model="deepseek-chat",
        api_key_env="DEEPSEEK_API_KEY",
        overrides=LLMOverrides(
            classifier=LLMStageOverride(provider="openai", model="gpt-x", api_key_env="OPENAI_KEY"),
            analyzer=LLMStageOverride(provider="claude", model="claude-x", api_key_env="ANTHROPIC_KEY"),
        ),
    )

    c = LLMFactory.create(cfg, stage="classifier")
    assert isinstance(c, OpenAICompatibleProvider)
    assert c.provider == "openai"
    assert c.model == "gpt-x"

    # Phase 1: claude 未实现时回退到主配置（deepseek）
    a = LLMFactory.create(cfg, stage="analyzer")
    assert isinstance(a, OpenAICompatibleProvider)
    assert a.provider == "deepseek"
    assert a.model == "deepseek-chat"


def test_llm_factory_supports_zai_provider() -> None:
    cfg = LLMConfig(provider="zai", model="glm-4-flash", api_key_env="ZHIPUAI_API_KEY")
    p = LLMFactory.create(cfg)
    assert isinstance(p, OpenAICompatibleProvider)
    assert p.provider == "zai"
    assert p.model == "glm-4-flash"


def test_openai_compat_default_base_url_for_zai(monkeypatch) -> None:
    monkeypatch.setenv("ZHIPUAI_API_KEY", "k")
    p = OpenAICompatibleProvider(
        provider="zai",
        model="glm-4-flash",
        api_key_env="ZHIPUAI_API_KEY",
        base_url=None,
        temperature=0.0,
        max_tokens=16,
    )
    assert p.base_url == "https://open.bigmodel.cn/api/paas/v4"


@respx.mock
async def test_zai_complete_calls_expected_endpoint(monkeypatch) -> None:
    monkeypatch.setenv("ZHIPUAI_API_KEY", "k")

    p = OpenAICompatibleProvider(
        provider="zai",
        model="glm-4-flash",
        api_key_env="ZHIPUAI_API_KEY",
        base_url=None,
        temperature=0.0,
        max_tokens=16,
    )

    route = respx.post("https://open.bigmodel.cn/api/paas/v4/chat/completions").mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "hello"}}]}),
    )

    out = await p.complete("hi")
    assert route.called
    assert out == "hello"

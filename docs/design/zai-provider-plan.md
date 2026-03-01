# audio-journal: z.ai (智谱 AI) Provider 支持实现计划

目标：在现有 LLM 抽象层（`src/audio_journal/llm/`）中新增对 z.ai（智谱 AI / BigModel）的支持，使其可以像 OpenAI / DeepSeek 一样通过统一接口调用。

约束与前提：
- 智谱 AI API **兼容 OpenAI Chat Completions** 形态。
- Base URL（官方）：`https://open.bigmodel.cn/api/paas/v4/`（注意不带 `/v1`）。
- 模型示例：`glm-4`、`glm-4-flash`、`glm-4-plus` 等。
- API Key 仍然只从环境变量读取（配置文件仅保存 env var 名称）。
- 本次只做“支持 z.ai”能力；不引入新的 Provider 协议类型（仍复用 OpenAI-compatible 实现）。

---

## 1. 代码改动点

### 1.1 扩展 OpenAICompatibleProvider 支持的 provider 枚举

文件：`src/audio_journal/llm/openai_compat.py`
- 在 `_default_base_url(provider: str)` 中新增分支：
  - `provider == "zai"` 时返回 `https://open.bigmodel.cn/api/paas/v4`
- 保持现有行为：
  - 继续使用 `Authorization: Bearer <API_KEY>`
  - endpoint 仍是 `POST {base_url}/chat/completions`
  - `base_url` 继续 `rstrip("/")`，避免拼接双斜杠

实现注意点（需要在实现阶段验证）：
- `json_mode` 当前通过 `response_format={"type":"json_object"}` 实现；需确认 z.ai 是否完全支持。
  - 若不支持，后续可加“兼容降级”策略（见测试与风险部分）。

### 1.2 放开 LLMFactory 对 zai provider 的创建

文件：`src/audio_journal/llm/base.py`
- 在 `LLMFactory.create()` 中，将现有允许集合从 `{"openai", "deepseek"}` 扩展为 `{"openai", "deepseek", "zai"}`。
- 仍然返回 `OpenAICompatibleProvider(...)`，仅 provider/model/base_url/api_key_env 不同。
- 保持现有“stage override 未实现 provider 时回退到默认 provider”的逻辑不变（claude override 仍会 fallback）。

### 1.3 文档/示例配置更新（建议做）

文件：
- `config.yaml`
- `docs/system-design.md`（provider 列表/示例）

改动建议：
- 在示例中补充 `zai` provider：
  - `llm.provider: zai`
  - `llm.model: glm-4-flash`（示例）
  - `llm.api_key_env: ZHIPUAI_API_KEY`（或团队约定的 env 名称，见配置项部分）
  - （可选）`llm.base_url: https://open.bigmodel.cn/api/paas/v4/`（不填则走默认）

---

## 2. 新增的配置项

原则：尽量不扩展配置结构，复用现有 `LLMConfig` 字段。

### 2.1 新增 provider 值：`zai`

- `llm.provider` 新增可选值：`zai`
- `llm.overrides.classifier.provider` / `llm.overrides.analyzer.provider` 同样允许 `zai`

### 2.2 API Key 环境变量

不新增字段，仍使用：
- `llm.api_key_env` / `llm.overrides.*.api_key_env`

建议约定（文档中写清楚即可）：
- 推荐 env var：`ZHIPUAI_API_KEY`（更贴近智谱生态常见命名）
- 如果团队内部更倾向 `ZAI_API_KEY` 也可，但需在文档中给出唯一推荐，避免混乱。

### 2.3 base_url

不新增字段，仍使用：
- `llm.base_url` / `llm.overrides.*.base_url`

默认值策略：
- 当 `provider == "zai"` 且未配置 `base_url` 时，自动使用：`https://open.bigmodel.cn/api/paas/v4`

### 2.4 配置示例（用于文档/README）

```yaml
llm:
  provider: zai
  model: glm-4-flash
  api_key_env: ZHIPUAI_API_KEY
  # base_url: https://open.bigmodel.cn/api/paas/v4/   # 可选：不填走默认
  temperature: 0.3
  max_tokens: 4096
  overrides:
    classifier:
      provider: zai
      model: glm-4-flash
    analyzer:
      provider: zai
      model: glm-4-plus
```

---

## 3. 测试策略

### 3.1 单元测试（必须）

文件：`tests/test_llm_provider.py`

新增/调整用例：
1. `test_llm_factory_supports_zai_provider()`
   - 构造 `LLMConfig(provider="zai", model="glm-4-flash", api_key_env="ZHIPUAI_API_KEY")`
   - 调用 `LLMFactory.create(cfg)`
   - 断言返回 `OpenAICompatibleProvider` 且 `provider == "zai"`、`model` 正确

2. `test_openai_compat_default_base_url_for_zai()`
   - 用 `OpenAICompatibleProvider(provider="zai", base_url=None, ...)`
   - 断言 `provider.base_url == "https://open.bigmodel.cn/api/paas/v4"`

3. `test_zai_complete_calls_expected_endpoint()`
   - 用 `respx` mock `POST https://open.bigmodel.cn/api/paas/v4/chat/completions`
   - monkeypatch 设置 `ZHIPUAI_API_KEY` 环境变量
   - 调用 `await provider.complete("hi")`
   - 断言 route 被调用且返回值能解析

### 3.2 兼容性/回归测试（必须）

- 现有 `test_llm_factory_overrides_and_fallback()` 继续保留，确保：
  - `openai/deepseek` 行为不变
  - `claude` override 仍然 fallback 到默认 provider（避免本次改动误触回归）

### 3.3 可选：集成测试（建议但不强制）

- 新增 `tests/test_llm_zai_integration.py`（标记 `@pytest.mark.integration`）：
  - 仅在本机设置了 `ZHIPUAI_API_KEY` 时运行
  - 发起一次真实 `chat/completions` 请求
  - 主要用于确认 `response_format`/`json_mode` 的兼容性

执行建议：
- 单测：`uv run pytest -q tests/test_llm_provider.py`
- 全量：`uv run pytest -q`

---

## 4. 向后兼容性考虑

- 这是“增量支持”变更：
  - 仅新增 provider 值 `zai` 与默认 base_url 映射
  - 不修改 `LLMConfig` 字段结构，不影响已有 `config.yaml` 用户
- `OpenAICompatibleProvider` 的行为对 `openai/deepseek` 不变。
- `LLMFactory` 的 fallback 逻辑不变：
  - 如果 stage override 使用未实现 provider（例如 `claude`），仍然回退到主配置 provider，避免阻塞 pipeline。

潜在风险与处理建议：
- 风险 1：z.ai 对 `response_format={"type":"json_object"}` 支持不完整，导致 json_mode 请求报错。
  - 建议在实现阶段增加“错误降级”策略（可选）：当 json_mode 请求返回 4xx 且报错与 response_format 相关时，自动重试一次（不带 response_format），并依赖 `parse_json_strict()` 解析。
  - 该策略应通过新增单测（mock 4xx -> retry -> 200）覆盖，避免改变其他 provider 行为。
- 风险 2：base_url 版本差异（`/v4` vs `/v1`）配置错误。
  - 文档明确：z.ai 使用 `https://open.bigmodel.cn/api/paas/v4/`；并在 provider 默认值中内置。

---

## 5. 实施顺序（建议）

1. 先补单测：新增 z.ai 相关用例（工厂选择、默认 base_url、请求 endpoint）。
2. 再实现代码：扩展 `_default_base_url()` 与 `LLMFactory.create()` provider 允许列表。
3. 跑全量测试，确认无回归。
4. 更新 `config.yaml` 与 `docs/system-design.md` 示例（可选但推荐）。

---

## 6. 验收标准

- 配置 `llm.provider: zai` 后，pipeline 可正常创建 provider 并完成一次 `complete()` 调用。
- 单测覆盖：z.ai 创建/默认 base_url/请求 endpoint；原有 provider 行为不变。
- 文档中有清晰的配置示例（含 env var 名称与 base_url 说明）。

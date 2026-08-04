# Integration Routing

**The router.** In Phase 2, fetch **only** the one page matching the detected stack — never the whole list. Every entry is a path under the base `https://arize.com/docs/ax/integrations/`; the full URL is `{base}{section-prefix}{entry}` (e.g. LLM providers → `…/integrations/llm-providers/openai/openai-tracing`).

Exhaustive for **tracing**. If a stack seems missing, confirm against the [integrations index](https://arize.com/docs/llms.txt) (this list can drift); if it's genuinely absent, there's no dedicated integration — use [manual instrumentation](https://arize.com/docs/ax/instrument/manual-instrumentation). Evaluator integrations are out of scope (see the `arize-evaluator` skill).

## LLM providers · `llm-providers/`
openai/openai-tracing · anthropic/anthropic-tracing · google-gen-ai/google-genai-tracing · amazon-bedrock/amazon-bedrock-tracing · amazon-bedrock/amazon-bedrock-agents-tracing · litellm/litellm-tracing · llama/ollama-tracing · groq/groq-tracing · mistralai/mistralai-tracing · openrouter/openrouter-tracing · orcarouter/orcarouter-tracing · truefoundry/truefoundry-tracing · doubleword/doubleword-tracing · vertexai/vertexai-tracing

## Python frameworks · `python-agent-frameworks/`
langchain/langchain-tracing · langgraph/langgraph-tracing · llamaindex/llamaindex-tracing · llamaindex/llamaindex-workflows-tracing · openai-agents/openai-agents-sdk-tracing · crewai/crewai-tracing · dspy/dspy-tracing · autogen/autogen-tracing · autogen/autogen-agentchat-tracing · aws-strands/aws-strands-tracing · aws-strands/bedrock-agentcore · beeai/beeai-tracing-python · claude-agent-sdk/claude-agent-sdk-tracing · google-adk/google-adk-tracing · guardrails-ai/guardrails-ai-tracing · haystack/haystack-tracing · hugging-face-smolagents/smolagents-tracing · instructor/instructor-tracing · microsoft/microsoft-agent-framework · model-context-protocol/mcp-tracing · nvidia/nemo-agent-toolkit-tracing · pipecat/pipecat-tracing · portkey/portkey-tracing · pydantic/pydantic-ai-tracing · semantic-kernel/semantic-kernel-tracing · together-ai/together-ai-tracing · agno/agno-tracing

## TypeScript / JavaScript · `ts-js-agent-frameworks/`
langchain/langchain-js · mastra/mastra-tracing · openai-agents/openai-agents-js · vercel/vercel-ai-sdk-tracing (AI SDK ≤ v6) · vercel/vercel-ai-sdk-v7-tracing (AI SDK v7+) · vercel/eve-tracing · beeai/beeai-tracing-js

## Java · `java/`
langchain4j/langchain4j-tracing · spring-ai/spring-ai-tracing · arconia/arconia-tracing · annotation/annotation-tracing

## Platforms & coding agents · `platforms/`
langflow/langflow-tracing · flowise/flowise-tracing · dify/dify-tracing · prompt-flow/prompt-flow-tracing · gemini/gemini-tracing · openrouter/openrouter-tracing · truefoundry/truefoundry-tracing · claude-code/claude-code-tracing · codex/codex-tracing · copilot/copilot-tracing · cursor/cursor-tracing · kiro/kiro-tracing · oh-my-pi/oh-my-pi-tracing · opencode/opencode-tracing

## OpenTelemetry & orchestration
`opentelemetry/`: openlit · openllmetry · traceloop-sdk · opentelemetry-arize-otel — bridges for apps already exporting OTel. `orchestration/`: airflow/airflow-provider · airflow/airflow-operators

## Go
No integration page — use [`arize-otel-go`](https://github.com/Arize-ai/arize-otel-go) `Register(ctx, Options)` plus a per-provider instrumentor ([openai-go](https://github.com/Arize-ai/openinference/tree/main/go/openinference-instrumentation-openai-go), [anthropic-sdk-go](https://github.com/Arize-ai/openinference/tree/main/go/openinference-instrumentation-anthropic-sdk-go)), or manual spans with [semantic-conventions](https://github.com/Arize-ai/openinference/tree/main/go/openinference-semantic-conventions). See [manual-spans.md](manual-spans.md).

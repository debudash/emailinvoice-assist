# Fixed Stages, with the only agent loop in context resolution

The pipeline is fixed Python Stages in a fixed order: extraction, context resolution, matching, decision, submission. It is not a single ReAct agent choosing what to do next, because the Stage order is a business rule, and the brief asks for observable state transitions and clear separation between Stages. Extraction, matching and the decision review are single structured LLM calls. The one agent loop is in context resolution: a LangChain tool-calling agent over the ref-mcp tools, because that is where the AI genuinely has to choose which lookups to make. The default stack's LangGraph is not used: append-only Stage Runs and rerunning from a Stage already give the pipeline durable state and resumability.

## Amendment (2026-10-19, during S0): Anthropic SDK instead of LangChain

The LLM calls use the Anthropic Python SDK directly, not LangChain. There are two reasons.
- **Forced tool calls:** LangChain's `with_structured_output` gets structured output by forcing a
  tool call, and `claude-opus-5-5` rejects forced `tool_choice` with a 400.
- **Sampling parameters:** the model also rejects sampling parameters such as `temperature`.

The SDK provides each piece we need:
- **Single structured calls:** native structured outputs (`messages.parse` with a pydantic model) for
  extraction, matching and the decision review.
- **The context agent:** the SDK's tool runner, with its MCP helper wrapping the ref-mcp tools. The
  runner can still return a validated structured answer.
- **Tracing:** LangSmith traces every call through `wrap_anthropic`, so observability is unchanged.

The shape of the decision stands: fixed Stages, one agent loop in context resolution. Only the
client library changed.

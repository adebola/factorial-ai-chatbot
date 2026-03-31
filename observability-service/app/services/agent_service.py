"""
LangChain agent service for observability queries.
Uses LangGraph's create_react_agent for tool-calling agent execution.
"""
import os
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from ..tools.base import BackendConfig
from ..tools.prometheus_query import PrometheusQueryTool
from ..tools.prometheus_discovery import PrometheusMetricDiscoveryTool
from ..tools.prometheus_alerts import PrometheusAlertsTool
from ..tools.elasticsearch_search import ElasticsearchSearchTool
from ..tools.jaeger_traces import JaegerTracesTool
from ..tools.k8s_resources import K8sResourcesTool
from ..tools.otel_metrics import OtelMetricsTool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert SRE assistant with access to observability tools for monitoring \
infrastructure and microservices.

IMPORTANT - Prometheus metrics workflow (follow these steps in order):
1. ALWAYS call prometheus_metric_discovery FIRST to find metric names. Do NOT guess metric names.
2. Before adding label filters, call prometheus_metric_discovery with metric_name="<exact_metric>" to discover \
available labels and their values. Do NOT guess label names like "pod" or "namespace" - different exporters use \
different labels (e.g. Spring Boot uses "application", "instance"; node_exporter uses "job", "instance").
3. The prometheus_query tool requires valid PromQL syntax - never pass natural language to it.
4. Use the exact metric names and label keys/values from discovery to construct PromQL:
   - Counters (ending in _total or _count): wrap with rate() or increase(), e.g. rate(http_requests_total[5m])
   - Gauges (e.g. process_cpu_usage, jvm_memory_used_bytes): query directly or use avg_over_time()
   - Histograms (_bucket suffix): use histogram_quantile() with rate()
5. If a query returns no results, re-check labels with discovery (metric_name=...) and retry with corrected filters

Efficiency tips (to minimize tool calls):
- Once you discover labels for one metric from a service, REUSE those same label keys/values for other \
metrics from the same service. For example, if process_cpu_usage has {application="order-service"}, then \
jvm_memory_used_bytes from the same service will also use {application="order-service"}.
- When asked about multiple metric types (e.g. CPU AND memory), discover ALL metric names in one call \
(without category filter or use name_pattern), then reuse labels across queries.
- JVM memory metrics (jvm_memory_used_bytes, jvm_memory_committed_bytes, jvm_memory_max_bytes) often have \
an "area" label with values "heap" and "nonheap". Query with area="heap" for main application memory.

IMPORTANT - Kubernetes resource lookups:
- Pod names in Kubernetes include random suffixes (e.g. order-service-7f8b9c6d4-x2k9m)
- The k8s_resources tool supports prefix/substring matching - pass the service name (e.g. "order-service") and it will match the full pod name
- Use action="list" with the name filter to see all matching pods before using "describe" or "logs"

When investigating issues:
1. Start with metrics and alerts for the big picture
2. Correlate findings: metrics -> traces -> logs -> K8s status
3. Provide root cause analysis with specific evidence (metric values, timestamps, trace IDs)
4. Suggest remediation steps when you have enough evidence

Guidelines:
- Be precise: include specific numbers, timestamps, and resource names
- When multiple tools could help, use them to cross-reference findings
- If a tool returns no results, state that clearly rather than guessing
- Summarize findings in a clear, actionable format
- If you cannot determine the root cause, say so and suggest next steps"""


@dataclass
class LLMConfig:
    """Configuration for the LLM provider."""
    provider: str = "openai"
    model: str = "gpt-4o"
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0


@dataclass
class AgentResult:
    """Result from an agent execution."""
    response: str
    tool_calls: List[Dict[str, Any]]
    total_duration_ms: float
    llm_tokens_used: Optional[int] = None
    status: str = "completed"
    error_message: Optional[str] = None


def _create_llm(config: LLMConfig):
    """Create an LLM instance based on provider configuration."""
    match config.provider:
        case "openai":
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=config.model,
                api_key=config.api_key or os.environ.get("OPENAI_API_KEY"),
                temperature=config.temperature
            )
        case "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=config.model,
                api_key=config.api_key or os.environ.get("ANTHROPIC_API_KEY"),
                temperature=config.temperature
            )
        case "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=config.model,
                base_url=config.base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                temperature=config.temperature
            )
        case "azure":
            from langchain_openai import AzureChatOpenAI
            return AzureChatOpenAI(
                model=config.model,
                api_key=config.api_key or os.environ.get("AZURE_OPENAI_API_KEY"),
                azure_endpoint=config.base_url or os.environ.get("AZURE_OPENAI_ENDPOINT"),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
                temperature=config.temperature
            )
        case _:
            raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _build_tools(backend_configs: Dict[str, BackendConfig]) -> list:
    """Build LangChain tools from backend configurations."""
    tools = []

    if "prometheus" in backend_configs:
        tools.append(PrometheusMetricDiscoveryTool(config=backend_configs["prometheus"]))
        tools.append(PrometheusQueryTool(config=backend_configs["prometheus"]))

    if "alertmanager" in backend_configs:
        tools.append(PrometheusAlertsTool(config=backend_configs["alertmanager"]))

    if "elasticsearch" in backend_configs:
        tools.append(ElasticsearchSearchTool(config=backend_configs["elasticsearch"]))

    if "jaeger" in backend_configs:
        tools.append(JaegerTracesTool(config=backend_configs["jaeger"]))

    if "kubernetes" in backend_configs:
        tools.append(K8sResourcesTool(config=backend_configs["kubernetes"]))

    if "otel_collector" in backend_configs:
        tools.append(OtelMetricsTool(config=backend_configs["otel_collector"]))

    return tools


def create_agent(
    backend_configs: Dict[str, BackendConfig],
    llm_config: LLMConfig
):
    """Create a LangGraph react agent with observability tools."""
    llm = _create_llm(llm_config)
    tools = _build_tools(backend_configs)

    if not tools:
        raise ValueError("No observability backends configured for this tenant")

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )

    return agent


async def execute_agent_query(
    backend_configs: Dict[str, BackendConfig],
    llm_config: LLMConfig,
    message: str,
    conversation_history: Optional[List[Dict[str, str]]] = None
) -> AgentResult:
    """Execute an observability query through the agent."""
    start_time = time.time()
    tool_calls = []

    try:
        agent = create_agent(backend_configs, llm_config)

        # Build messages from conversation history
        messages = []
        if conversation_history:
            for msg in conversation_history:
                if msg.get("role") == "user":
                    messages.append(HumanMessage(content=msg["content"]))
                elif msg.get("role") == "assistant":
                    messages.append(AIMessage(content=msg["content"]))

        # Add current user message
        messages.append(HumanMessage(content=message))

        # Execute the agent with recursion limit (controls max tool iterations)
        # Each tool call uses ~2 graph steps (LLM node + tool node).
        # Complex queries (K8s + multiple metrics) need 7+ tool calls.
        result = await agent.ainvoke(
            {"messages": messages},
            config={"recursion_limit": 40}
        )

        # Extract tool call details and log LLM reasoning chain
        all_messages = result.get("messages", [])
        step = 0
        for msg in all_messages:
            if isinstance(msg, AIMessage) and msg.tool_calls:
                step += 1
                # Log the LLM's reasoning before tool invocation
                if msg.content:
                    logger.debug(
                        f"[Step {step}] LLM reasoning: {msg.content}",
                        extra={"step": step, "tool_count": len(msg.tool_calls)}
                    )
                for tc in msg.tool_calls:
                    logger.debug(
                        f"[Step {step}] LLM decided to call: {tc['name']}({tc['args']})",
                        extra={"step": step, "tool": tc["name"], "tool_args": tc["args"]}
                    )
                    tool_calls.append({
                        "tool": tc["name"],
                        "input": tc["args"] if isinstance(tc["args"], dict) else {"query": tc["args"]},
                        "output": "",  # Will be filled from ToolMessage
                        "duration_ms": 0
                    })
            elif isinstance(msg, ToolMessage):
                # Log tool result preview
                result_preview = str(msg.content)[:300]
                logger.debug(
                    f"[Step {step}] Tool result [{msg.name}]: {result_preview}",
                    extra={"step": step, "tool": msg.name, "result_length": len(str(msg.content))}
                )
                # Match tool message to the last tool call with empty output
                for tc_detail in reversed(tool_calls):
                    if tc_detail["output"] == "" and tc_detail["tool"] == msg.name:
                        tc_detail["output"] = str(msg.content)[:2000]
                        break

        # Get the final AI response (last AIMessage without tool calls)
        response_text = ""
        for msg in reversed(all_messages):
            if isinstance(msg, AIMessage) and not msg.tool_calls and msg.content:
                response_text = msg.content
                break

        # Fallback: if the LLM didn't produce a final summary (common with smaller
        # local models), synthesise a response from tool call outputs so the user
        # still gets useful information.
        if not response_text and tool_calls:
            logger.warning(f"The LLM did produce a final summary Provider: {llm_config.provider}, Model {llm_config.model}")
            parts = []
            for tc in tool_calls:
                output = tc.get("output", "")
                if output:
                    parts.append(f"**{tc['tool']}** ({', '.join(f'{k}={v}' for k, v in tc['input'].items())}):\n{output}")
            if parts:
                response_text = "Here are the results from the observability tools:\n\n" + "\n\n".join(parts)

        total_duration_ms = (time.time() - start_time) * 1000

        # Log agent loop summary
        tool_names = [tc["tool"] for tc in tool_calls]
        logger.debug(
            f"Agent completed: {len(all_messages)} messages, {len(tool_calls)} tool calls "
            f"{tool_names}, {total_duration_ms:.0f}ms",
            extra={
                "message_count": len(all_messages),
                "tool_count": len(tool_calls),
                "tools_used": tool_names,
                "duration_ms": total_duration_ms
            }
        )

        return AgentResult(
            response=response_text,
            tool_calls=tool_calls,
            total_duration_ms=total_duration_ms,
            status="completed"
        )

    except Exception as e:
        total_duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        return AgentResult(
            response="",
            tool_calls=tool_calls,
            total_duration_ms=total_duration_ms,
            status="error",
            error_message=str(e)
        )

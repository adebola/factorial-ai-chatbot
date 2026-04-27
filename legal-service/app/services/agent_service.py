"""
LangGraph ReAct agent service for legal intelligence queries.

Follows the same pattern as the observability-service agent_service.py:
create_react_agent from LangGraph, tool-calling loop, structured result.
"""
import os
import time
import logging
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage

from ..tools.base import LegalToolConfig
from ..tools.document_list import DocumentListTool
from ..tools.workspace_search import WorkspaceSearchTool
from ..tools.contract_analysis import ContractAnalysisTool
from ..tools.contract_dates import ContractDatesTool
from ..tools.contract_compare import ContractCompareTool

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a senior Nigerian legal advisor with expertise in contract law, \
commercial transactions, regulatory compliance, and dispute resolution.

You have access to tools that let you search and analyse legal documents in the user's workspace.

IMPORTANT — Workflow (follow these steps in order):
1. ALWAYS call document_list FIRST to see what documents are available in the workspace.
2. Use workspace_search for general legal questions, finding specific clauses, or locating provisions.
3. Use contract_analysis for structured analysis: summarize, obligations, risk_flags, or missing_clauses.
4. Use contract_dates to extract a timeline of dates, deadlines, and notice periods from a specific document.
5. Use contract_compare to compare two documents side-by-side and identify material differences.

CRITICAL RULES:
- All output is ADVISORY. The instructing lawyer reviews all output and takes professional \
responsibility. Always state this disclaimer when providing substantive legal analysis.
- CITE SOURCES: Every factual claim must reference the source document name and page number. \
Never state a fact from a document without attribution.
- Use correct Nigerian legal terminology (e.g. "Arbitration and Mediation Act 2023", \
"Nigeria Data Protection Act 2023", "Companies and Allied Matters Act 2020").
- For contract analysis: perform clause-by-clause review and flag deviations from standard \
Nigerian commercial practice.
- If a document is poorly drafted or missing standard clauses under Nigerian law, say so explicitly.
- When multiple documents are involved, clearly distinguish which document each finding comes from.
- If you cannot find information to answer the question, say so — do not fabricate legal advice.

Guidelines:
- Be precise: include specific clause numbers, section references, and page numbers.
- When performing risk analysis, rate each risk as HIGH / MEDIUM / LOW.
- For missing clauses, explain why each matters under Nigerian law and suggest remedy.
- Summarise findings in a clear, actionable format suitable for a practising lawyer."""


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
                temperature=config.temperature,
            )
        case "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=config.model,
                api_key=config.api_key or os.environ.get("ANTHROPIC_API_KEY"),
                temperature=config.temperature,
            )
        case "ollama":
            from langchain_ollama import ChatOllama
            return ChatOllama(
                model=config.model,
                base_url=config.base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
                temperature=config.temperature,
            )
        case "azure":
            from langchain_openai import AzureChatOpenAI
            return AzureChatOpenAI(
                model=config.model,
                api_key=config.api_key or os.environ.get("AZURE_OPENAI_API_KEY"),
                azure_endpoint=config.base_url or os.environ.get("AZURE_OPENAI_ENDPOINT"),
                api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
                temperature=config.temperature,
            )
        case _:
            raise ValueError(f"Unsupported LLM provider: {config.provider}")


def _build_tools(config: LegalToolConfig) -> list:
    """Build all legal analysis tools for the given workspace."""
    return [
        DocumentListTool(config=config),
        WorkspaceSearchTool(config=config),
        ContractAnalysisTool(config=config),
        ContractDatesTool(config=config),
        ContractCompareTool(config=config),
    ]


def create_agent(tool_config: LegalToolConfig, llm_config: LLMConfig):
    """Create a LangGraph ReAct agent with legal tools."""
    llm = _create_llm(llm_config)
    tools = _build_tools(tool_config)

    agent = create_react_agent(
        model=llm,
        tools=tools,
        prompt=SYSTEM_PROMPT,
    )

    return agent


async def execute_query(
    tenant_id: str,
    workspace_id: str,
    message: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    access_token: Optional[str] = None,
    llm_config: Optional[LLMConfig] = None,
) -> Dict[str, Any]:
    """Execute a legal query through the agent.

    Returns a dict with keys: response, tool_calls, total_duration_ms.
    """
    start_time = time.time()
    tool_calls: List[Dict[str, Any]] = []

    if llm_config is None:
        llm_config = LLMConfig()

    tool_config = LegalToolConfig(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        access_token=access_token,
    )

    try:
        agent = create_agent(tool_config, llm_config)

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

        # Execute the agent — legal analysis may need several tool calls
        result = await agent.ainvoke(
            {"messages": messages},
            config={"recursion_limit": 40},
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
                        extra={"step": step, "tool_count": len(msg.tool_calls)},
                    )
                for tc in msg.tool_calls:
                    logger.debug(
                        f"[Step {step}] LLM decided to call: {tc['name']}({tc['args']})",
                        extra={"step": step, "tool": tc["name"], "tool_args": tc["args"]},
                    )
                    tool_calls.append({
                        "tool": tc["name"],
                        "input": tc["args"] if isinstance(tc["args"], dict) else {"query": tc["args"]},
                        "output": "",
                    })
            elif isinstance(msg, ToolMessage):
                # Log tool result preview
                result_preview = str(msg.content)[:300]
                logger.debug(
                    f"[Step {step}] Tool result [{msg.name}]: {result_preview}",
                    extra={"step": step, "tool": msg.name, "result_length": len(str(msg.content))},
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

        # Fallback: synthesise from tool outputs if LLM didn't produce a summary
        if not response_text and tool_calls:
            logger.warning(
                f"LLM did not produce a final summary. Provider: {llm_config.provider}, "
                f"Model: {llm_config.model}"
            )
            parts = []
            for tc in tool_calls:
                output = tc.get("output", "")
                if output:
                    parts.append(
                        f"**{tc['tool']}** "
                        f"({', '.join(f'{k}={v}' for k, v in tc['input'].items())}):\n{output}"
                    )
            if parts:
                response_text = (
                    "Here are the results from the legal analysis tools:\n\n"
                    + "\n\n".join(parts)
                )

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
                "duration_ms": total_duration_ms,
            },
        )

        return {
            "response": response_text,
            "tool_calls": tool_calls,
            "total_duration_ms": total_duration_ms,
        }

    except Exception as e:
        total_duration_ms = (time.time() - start_time) * 1000
        logger.error(f"Agent execution failed: {e}", exc_info=True)
        return {
            "response": "",
            "tool_calls": tool_calls,
            "total_duration_ms": total_duration_ms,
            "error": str(e),
        }

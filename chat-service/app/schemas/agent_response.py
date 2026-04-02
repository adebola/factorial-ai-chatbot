"""Structured response protocol for agentic services.

Defines the content block types that agents can return for rich
rendering in the frontend. The same blocks power document export
(PDF, PPTX, DOCX) in Phase 4.

Each AgentMessage stores both:
- content: plain text for LLM context replay (token-counted)
- structured_blocks: list of ContentBlock dicts for UI rendering
"""
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class BlockType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    DIAGRAM = "diagram"
    CODE = "code"
    IMAGE = "image"
    ALERT = "alert"


class ContentBlock(BaseModel):
    """A single renderable content block in an agent response."""
    type: BlockType
    content: Optional[str] = None          # text, diagram source, code content
    data: Optional[Dict[str, Any]] = None  # table rows/headers, chart datasets
    language: Optional[str] = None         # for code blocks (python, yaml, json, etc.)
    format: Optional[str] = None           # for diagrams (mermaid, d3, plantuml)
    chart_type: Optional[str] = None       # line, bar, pie, area, scatter
    url: Optional[str] = None              # for images
    alt: Optional[str] = None              # image alt text
    severity: Optional[str] = None         # for alerts: info, warning, error, success


class ToolCallDetail(BaseModel):
    """Detail of a single tool invocation by the agent."""
    tool: str
    input: Optional[Dict[str, Any]] = None
    output: Optional[str] = None
    duration_ms: Optional[float] = None


class TokenUsage(BaseModel):
    """Token usage reported by the agent."""
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class AgentQueryResponse(BaseModel):
    """
    Structured response from an agentic service.

    Agents return this format so the gateway can store both the plain
    text (for context replay) and structured blocks (for rich rendering).
    """
    response: str                                  # plain text summary (for LLM context)
    response_type: str = "rich"                    # "plain" or "rich"
    blocks: List[ContentBlock] = []                # structured content for UI
    tool_calls: List[ToolCallDetail] = []
    suggested_actions: List[str] = []              # e.g. ["Export as PDF", "Investigate further"]
    token_usage: Optional[TokenUsage] = None
    query_id: Optional[str] = None
    total_duration_ms: Optional[float] = None

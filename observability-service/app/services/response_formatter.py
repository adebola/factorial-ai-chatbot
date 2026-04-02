"""Transform agent tool results into structured content blocks.

Converts raw tool outputs from Prometheus, Kubernetes, Elasticsearch,
Jaeger, and OTel into typed blocks (text, table, code, chart, alert)
for rich rendering in the frontend.
"""
import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def format_tool_result(tool_name: str, tool_input: Dict[str, Any], tool_output: str) -> List[dict]:
    """
    Convert a single tool call result into structured content blocks.

    Returns a list of block dicts matching the ContentBlock schema:
    {"type": "text|table|code|chart|alert", ...}
    """
    try:
        if tool_name in ("prometheus_query",):
            return _format_prometheus_query(tool_input, tool_output)
        elif tool_name in ("prometheus_metric_discovery",):
            return _format_prometheus_discovery(tool_output)
        elif tool_name in ("prometheus_alerts",):
            return _format_alerts(tool_output)
        elif tool_name in ("search_logs", "elasticsearch_search"):
            return _format_logs(tool_output)
        elif tool_name in ("jaeger_traces", "get_traces"):
            return _format_traces(tool_output)
        elif tool_name in ("k8s_resources", "get_kubernetes_resources"):
            return _format_kubernetes(tool_output)
        elif tool_name in ("get_pod_logs",):
            return _format_pod_logs(tool_output)
        elif tool_name in ("otel_metrics",):
            return _format_prometheus_query(tool_input, tool_output)
        else:
            return _format_generic(tool_name, tool_output)
    except Exception as e:
        logger.warning(f"Failed to format tool result for {tool_name}: {e}")
        return _format_generic(tool_name, tool_output)


def format_full_response(
    response_text: str,
    tool_calls: List[Dict[str, Any]],
) -> List[dict]:
    """
    Build the complete list of structured blocks for an agent response.

    Interleaves text blocks from the agent's narrative with formatted
    tool result blocks.
    """
    blocks = []

    # Add the agent's text response as the primary block
    if response_text:
        blocks.append({"type": "text", "content": response_text})

    # Add formatted tool results
    for tc in tool_calls:
        tool_blocks = format_tool_result(
            tool_name=tc.get("tool", ""),
            tool_input=tc.get("input", {}),
            tool_output=tc.get("output", ""),
        )
        blocks.extend(tool_blocks)

    return blocks


# ── Prometheus ──

def _format_prometheus_query(tool_input: Dict[str, Any], output: str) -> List[dict]:
    """Format Prometheus query results as table + optional chart data."""
    blocks = []

    # Try to parse structured data from the output
    data = _try_parse_json(output)
    if data and isinstance(data, list):
        # Time series data → table + chart
        if data and isinstance(data[0], dict):
            headers = list(data[0].keys())
            rows = [list(item.values()) for item in data]
            blocks.append({
                "type": "table",
                "data": {"headers": headers, "rows": rows},
            })
            # If there's a time/value pattern, add chart data
            if any(k in headers for k in ("timestamp", "time", "__name__")):
                blocks.append({
                    "type": "chart",
                    "chart_type": "line",
                    "data": {"series": data},
                })
            return blocks

    # Fallback: render as code block with the PromQL query as context
    promql = tool_input.get("promql", "")
    if promql:
        blocks.append({"type": "code", "language": "promql", "content": promql})
    if output:
        blocks.append({"type": "code", "language": "text", "content": _truncate(output, 3000)})

    return blocks


def _format_prometheus_discovery(output: str) -> List[dict]:
    """Format metric discovery results as a table."""
    blocks = []
    data = _try_parse_json(output)
    if data and isinstance(data, list):
        if data and isinstance(data[0], dict):
            headers = list(data[0].keys())
            rows = [list(item.values()) for item in data[:50]]  # Cap at 50 metrics
            blocks.append({"type": "table", "data": {"headers": headers, "rows": rows}})
            return blocks

    # Fallback
    blocks.append({"type": "code", "language": "text", "content": _truncate(output, 3000)})
    return blocks


def _format_alerts(output: str) -> List[dict]:
    """Format Prometheus alerts as alert blocks + table."""
    blocks = []
    data = _try_parse_json(output)

    if data and isinstance(data, list):
        for alert in data[:10]:  # Cap at 10 alerts
            if isinstance(alert, dict):
                severity = alert.get("severity", alert.get("labels", {}).get("severity", "warning"))
                name = alert.get("alertname", alert.get("labels", {}).get("alertname", "Alert"))
                message = alert.get("annotations", {}).get("summary", alert.get("state", ""))
                blocks.append({
                    "type": "alert",
                    "severity": severity,
                    "content": f"**{name}**: {message}",
                })
        return blocks

    # Fallback
    if "firing" in output.lower() or "alert" in output.lower():
        blocks.append({"type": "alert", "severity": "warning", "content": _truncate(output, 1000)})
    else:
        blocks.append({"type": "text", "content": _truncate(output, 2000)})
    return blocks


# ── Kubernetes ──

def _format_kubernetes(output: str) -> List[dict]:
    """Format Kubernetes resource info as table or YAML code block."""
    blocks = []
    data = _try_parse_json(output)

    if data and isinstance(data, list) and data and isinstance(data[0], dict):
        # Tabular resource data (pods, deployments, services, etc.)
        headers = list(data[0].keys())
        rows = [list(item.values()) for item in data[:30]]
        blocks.append({"type": "table", "data": {"headers": headers, "rows": rows}})
        return blocks

    if data and isinstance(data, dict):
        # Single resource → YAML-like display
        blocks.append({"type": "code", "language": "yaml", "content": _dict_to_yaml(data)})
        return blocks

    # Fallback: render as code
    if output.strip().startswith(("{", "[")):
        blocks.append({"type": "code", "language": "json", "content": _truncate(output, 3000)})
    else:
        blocks.append({"type": "code", "language": "text", "content": _truncate(output, 3000)})
    return blocks


def _format_pod_logs(output: str) -> List[dict]:
    """Format pod logs as a code block."""
    return [{"type": "code", "language": "log", "content": _truncate(output, 5000)}]


# ── Elasticsearch / Logs ──

def _format_logs(output: str) -> List[dict]:
    """Format log search results as a code block or table."""
    blocks = []
    data = _try_parse_json(output)

    if data and isinstance(data, list) and data and isinstance(data[0], dict):
        # Structured log entries → table
        headers = list(data[0].keys())
        rows = [list(item.values()) for item in data[:30]]
        blocks.append({"type": "table", "data": {"headers": headers, "rows": rows}})
        return blocks

    # Raw log output → code block
    blocks.append({"type": "code", "language": "log", "content": _truncate(output, 5000)})
    return blocks


# ── Jaeger / Traces ──

def _format_traces(output: str) -> List[dict]:
    """Format distributed trace data as a table."""
    blocks = []
    data = _try_parse_json(output)

    if data and isinstance(data, list) and data and isinstance(data[0], dict):
        headers = list(data[0].keys())
        rows = [list(item.values()) for item in data[:30]]
        blocks.append({"type": "table", "data": {"headers": headers, "rows": rows}})
        return blocks

    blocks.append({"type": "code", "language": "json", "content": _truncate(output, 3000)})
    return blocks


# ── Generic ──

def _format_generic(tool_name: str, output: str) -> List[dict]:
    """Generic formatter for unknown tool types."""
    if not output:
        return []

    # Try to detect if it's JSON
    data = _try_parse_json(output)
    if data:
        if isinstance(data, list) and data and isinstance(data[0], dict):
            headers = list(data[0].keys())
            rows = [list(item.values()) for item in data[:30]]
            return [{"type": "table", "data": {"headers": headers, "rows": rows}}]
        elif isinstance(data, dict):
            return [{"type": "code", "language": "json", "content": json.dumps(data, indent=2)[:3000]}]

    return [{"type": "code", "language": "text", "content": _truncate(output, 3000)}]


# ── Utilities ──

def _try_parse_json(text: str) -> Optional[Any]:
    """Attempt to parse JSON from text, returning None on failure."""
    if not text:
        return None
    text = text.strip()
    # Handle common wrapping patterns
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "\n... (truncated)"


def _dict_to_yaml(d: dict, indent: int = 0) -> str:
    """Simple dict-to-YAML-like string for display."""
    lines = []
    prefix = "  " * indent
    for key, value in d.items():
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            lines.append(_dict_to_yaml(value, indent + 1))
        elif isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{prefix}- ")
                    lines.append(_dict_to_yaml(item, indent + 2))
                else:
                    lines.append(f"{prefix}- {item}")
        else:
            lines.append(f"{prefix}{key}: {value}")
    return "\n".join(lines)

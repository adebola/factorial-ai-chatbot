"""
Elasticsearch search tool - searches logs using natural language descriptions.
"""
import logging
from typing import Type, Optional
from datetime import datetime, timedelta

import httpx
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import BackendConfig

logger = logging.getLogger(__name__)


class ElasticsearchSearchInput(BaseModel):
    """Input for Elasticsearch search tool."""
    description: str = Field(description="Natural language description of what to search for in logs, e.g. 'errors in payments service' or 'connection timeout messages'")
    time_range: str = Field(default="1h", description="Time range to search, e.g. '15m', '1h', '6h', '24h'")
    service: Optional[str] = Field(default=None, description="Filter by service/application name")
    log_level: Optional[str] = Field(default=None, description="Filter by log level: 'ERROR', 'WARN', 'INFO', 'DEBUG'")


def _parse_time_range_ms(time_range: str) -> int:
    """Parse time range to milliseconds ago from now."""
    unit = time_range[-1]
    value = int(time_range[:-1])
    match unit:
        case 'm':
            return value * 60 * 1000
        case 'h':
            return value * 3600 * 1000
        case 'd':
            return value * 86400 * 1000
        case _:
            return 3600 * 1000


class ElasticsearchSearchTool(BaseTool):
    """Search application logs in Elasticsearch.

    Use this to find error messages, trace log patterns, and correlate
    log events across services.
    """
    name: str = "elasticsearch_search"
    description: str = (
        "Search application logs in Elasticsearch. Use this to find error messages, "
        "trace specific events, or correlate log entries across services. "
        "Provide a natural language description of what to search for."
    )
    args_schema: Type[BaseModel] = ElasticsearchSearchInput
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _build_query(self, description: str, time_range: str,
                     service: str = None, log_level: str = None) -> dict:
        """Build an Elasticsearch DSL query from the description."""
        time_range_ms = _parse_time_range_ms(time_range)

        must_clauses = [
            {
                "range": {
                    "@timestamp": {
                        "gte": f"now-{time_range}",
                        "lte": "now"
                    }
                }
            }
        ]

        # Add text search
        must_clauses.append({
            "multi_match": {
                "query": description,
                "fields": ["message", "log", "msg", "error", "error.message", "kubernetes.pod_name"],
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        })

        if service:
            must_clauses.append({
                "bool": {
                    "should": [
                        {"term": {"kubernetes.container_name": service}},
                        {"term": {"service.name": service}},
                        {"term": {"app": service}},
                        {"wildcard": {"kubernetes.pod_name": f"*{service}*"}}
                    ],
                    "minimum_should_match": 1
                }
            })

        if log_level:
            must_clauses.append({
                "bool": {
                    "should": [
                        {"term": {"level": log_level.upper()}},
                        {"term": {"log.level": log_level.upper()}},
                        {"term": {"severity": log_level.upper()}}
                    ],
                    "minimum_should_match": 1
                }
            })

        return {
            "size": 50,
            "sort": [{"@timestamp": {"order": "desc"}}],
            "query": {
                "bool": {
                    "must": must_clauses
                }
            },
            "_source": ["@timestamp", "message", "log", "msg", "level", "severity",
                        "kubernetes.pod_name", "kubernetes.container_name",
                        "kubernetes.namespace_name", "service.name", "error", "trace_id"]
        }

    def _run(self, description: str, time_range: str = "1h",
             service: str = None, log_level: str = None) -> str:
        """Execute the Elasticsearch search."""
        try:
            query = self._build_query(description, time_range, service, log_level)

            # Try common index patterns
            index_patterns = ["*-logs-*", "logs-*", "filebeat-*", "logstash-*", "*"]

            for index_pattern in index_patterns:
                try:
                    response = httpx.post(
                        f"{self.config.url}/{index_pattern}/_search",
                        json=query,
                        headers=self.config.get_headers(),
                        verify=self.config.verify_ssl,
                        timeout=self.config.timeout_seconds,
                        auth=self.config.get_auth_tuple()
                    )

                    if response.status_code == 200:
                        data = response.json()
                        hits = data.get("hits", {})
                        total = hits.get("total", {})
                        total_count = total.get("value", 0) if isinstance(total, dict) else total
                        entries = hits.get("hits", [])

                        if entries:
                            return self._format_results(entries, total_count, index_pattern, time_range)

                    elif response.status_code == 404:
                        continue  # Try next index pattern
                    else:
                        continue

                except Exception:
                    continue

            return f"No log entries found matching '{description}' in the last {time_range}"

        except httpx.TimeoutException:
            return f"Elasticsearch search timed out after {self.config.timeout_seconds}s"
        except httpx.ConnectError as e:
            return f"Cannot connect to Elasticsearch at {self.config.url}: {e}"
        except Exception as e:
            return f"Elasticsearch search error: {str(e)}"

    def _format_results(self, entries: list, total_count: int,
                        index: str, time_range: str) -> str:
        """Format Elasticsearch results into readable output."""
        output_lines = [
            f"Log Search Results (showing {len(entries)} of {total_count} total, last {time_range}):",
            f"Index: {index}"
        ]

        for i, entry in enumerate(entries[:30]):
            source = entry.get("_source", {})
            timestamp = source.get("@timestamp", "unknown")
            message = source.get("message") or source.get("log") or source.get("msg", "")
            level = source.get("level") or source.get("severity", "")
            pod = source.get("kubernetes", {}).get("pod_name", "")
            container = source.get("kubernetes", {}).get("container_name", "")
            namespace = source.get("kubernetes", {}).get("namespace_name", "")
            service_name = source.get("service", {}).get("name", "") if isinstance(source.get("service"), dict) else ""
            trace_id = source.get("trace_id", "")

            # Truncate long messages
            if len(str(message)) > 300:
                message = str(message)[:300] + "..."

            source_label = pod or container or service_name or ""
            output_lines.append(
                f"  [{i+1}] [{timestamp}] [{level}] {source_label}"
            )
            if namespace:
                output_lines.append(f"       namespace: {namespace}")
            output_lines.append(f"       {message}")
            if trace_id:
                output_lines.append(f"       trace_id: {trace_id}")

        if total_count > 30:
            output_lines.append(f"  ... {total_count - 30} more entries not shown")

        return "\n".join(output_lines)

"""
Prometheus query tool - generates PromQL from natural language and executes it.
"""
import logging
from typing import Type
from datetime import datetime, timedelta, timezone

import httpx
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import BackendConfig

logger = logging.getLogger(__name__)


class PrometheusQueryInput(BaseModel):
    """Input for Prometheus query tool."""
    description: str = Field(description="Natural language description of the metric to query, e.g. 'CPU usage for payments service over last hour'")
    time_range: str = Field(default="1h", description="Time range to query, e.g. '15m', '1h', '6h', '24h', '7d'")


def _parse_time_range(time_range: str) -> timedelta:
    """Parse a time range string like '1h', '30m', '7d' to timedelta."""
    unit = time_range[-1]
    value = int(time_range[:-1])
    match unit:
        case 'm':
            return timedelta(minutes=value)
        case 'h':
            return timedelta(hours=value)
        case 'd':
            return timedelta(days=value)
        case _:
            return timedelta(hours=1)


class PrometheusQueryTool(BaseTool):
    """Query Prometheus metrics using natural language descriptions.

    This tool translates natural language metric descriptions into PromQL queries,
    executes them against Prometheus, and returns formatted results.
    """
    name: str = "prometheus_query"
    description: str = (
        "Query Prometheus metrics. Use this to check CPU usage, memory, request rates, "
        "error rates, latency percentiles, and other time-series metrics. "
        "Provide a natural language description of what metric you want."
    )
    args_schema: Type[BaseModel] = PrometheusQueryInput
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _build_promql(self, description: str, time_range: str) -> str:
        """Build a PromQL query from the description.

        Uses heuristics to map common descriptions to PromQL patterns.
        For production, this would use an LLM to generate the PromQL.
        """
        # Check for raw PromQL first (contains query syntax characters)
        if any(op in description for op in ['{', '}', '(', ')', 'histogram']):
            return description

        desc_lower = description.lower()

        if "cpu" in desc_lower:
            if "node" in desc_lower:
                return f'100 - (avg by(instance) (rate(node_cpu_seconds_total{{mode="idle"}}[{time_range}])) * 100)'
            service = self._extract_service(desc_lower)
            if service:
                return f'rate(container_cpu_usage_seconds_total{{pod=~"{service}.*"}}[{time_range}])'
            return f'rate(container_cpu_usage_seconds_total[{time_range}])'

        if "memory" in desc_lower or "mem" in desc_lower:
            service = self._extract_service(desc_lower)
            if service:
                return f'container_memory_usage_bytes{{pod=~"{service}.*"}}'
            return 'container_memory_usage_bytes'

        if "latency" in desc_lower or "p99" in desc_lower or "p95" in desc_lower:
            service = self._extract_service(desc_lower)
            percentile = "0.99" if "p99" in desc_lower else "0.95"
            if service:
                return f'histogram_quantile({percentile}, rate(http_request_duration_seconds_bucket{{service="{service}"}}[{time_range}]))'
            return f'histogram_quantile({percentile}, rate(http_request_duration_seconds_bucket[{time_range}]))'

        if "error" in desc_lower or "5xx" in desc_lower or "500" in desc_lower:
            service = self._extract_service(desc_lower)
            if service:
                return f'rate(http_requests_total{{service="{service}",status=~"5.."}}[{time_range}])'
            return f'rate(http_requests_total{{status=~"5.."}}[{time_range}])'

        if "request" in desc_lower and ("rate" in desc_lower or "rps" in desc_lower or "throughput" in desc_lower):
            service = self._extract_service(desc_lower)
            if service:
                return f'rate(http_requests_total{{service="{service}"}}[{time_range}])'
            return f'rate(http_requests_total[{time_range}])'

        if "restart" in desc_lower:
            service = self._extract_service(desc_lower)
            if service:
                return f'kube_pod_container_status_restarts_total{{pod=~"{service}.*"}}'
            return 'kube_pod_container_status_restarts_total'

        if "disk" in desc_lower or "storage" in desc_lower:
            return 'node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}'

        # Generic: try to use it as a metric name pattern
        return f'{{__name__=~".*{description.replace(" ", ".*")}.*"}}'

    def _extract_service(self, desc_lower: str) -> str:
        """Extract service name from description."""
        # Look for common patterns like "for <service>" or "<service> service"
        for keyword in ["for ", "of ", "on ", "from "]:
            if keyword in desc_lower:
                parts = desc_lower.split(keyword)
                if len(parts) > 1:
                    service = parts[-1].strip().split()[0].rstrip('.,;')
                    if service and service not in ("the", "all", "each", "every", "last"):
                        return service
        return ""

    def _run(self, description: str, time_range: str = "1h") -> str:
        """Execute the Prometheus query synchronously."""
        try:
            promql = self._build_promql(description, time_range)
            td = _parse_time_range(time_range)
            end = datetime.now(timezone.utc)
            start = end - td
            step = max(int(td.total_seconds() / 100), 15)

            params = {
                "query": promql,
                "start": start.isoformat() + "Z",
                "end": end.isoformat() + "Z",
                "step": f"{step}s"
            }

            response = httpx.get(
                f"{self.config.url}/api/v1/query_range",
                params=params,
                headers=self.config.get_headers(),
                verify=self.config.verify_ssl,
                timeout=self.config.timeout_seconds,
                auth=self.config.get_auth_tuple()
            )

            if response.status_code != 200:
                # Self-correction: try instant query
                params_instant = {"query": promql}
                response = httpx.get(
                    f"{self.config.url}/api/v1/query",
                    params=params_instant,
                    headers=self.config.get_headers(),
                    verify=self.config.verify_ssl,
                    timeout=self.config.timeout_seconds,
                    auth=self.config.get_auth_tuple()
                )
                if response.status_code != 200:
                    return f"Prometheus query failed (status {response.status_code}): {response.text[:500]}"

            data = response.json()
            if data.get("status") != "success":
                error_msg = data.get("error", "Unknown error")
                return f"PromQL error for query '{promql}': {error_msg}"

            results = data.get("data", {}).get("result", [])
            if not results:
                return f"No results for PromQL: {promql} (time range: {time_range})"

            # Format results
            output_lines = [f"PromQL: {promql}", f"Time range: {time_range}", f"Results ({len(results)} series):"]
            for i, series in enumerate(results[:20]):  # Limit to 20 series
                metric = series.get("metric", {})
                metric_label = ", ".join(f'{k}="{v}"' for k, v in metric.items() if k != "__name__")
                metric_name = metric.get("__name__", "")
                label = f"{metric_name}{{{metric_label}}}" if metric_label else metric_name

                values = series.get("values", [])
                if values:
                    latest_val = values[-1][1]
                    first_val = values[0][1]
                    output_lines.append(f"  [{i+1}] {label}: current={latest_val}, start={first_val} ({len(values)} data points)")
                else:
                    value = series.get("value", [None, None])
                    output_lines.append(f"  [{i+1}] {label}: value={value[1] if len(value) > 1 else 'N/A'}")

            if len(results) > 20:
                output_lines.append(f"  ... and {len(results) - 20} more series")

            return "\n".join(output_lines)

        except httpx.TimeoutException:
            return f"Prometheus query timed out after {self.config.timeout_seconds}s"
        except httpx.ConnectError as e:
            return f"Cannot connect to Prometheus at {self.config.url}: {e}"
        except Exception as e:
            return f"Prometheus query error: {str(e)}"

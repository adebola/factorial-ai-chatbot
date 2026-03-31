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
    promql: str = Field(description="A valid PromQL expression to execute, e.g. 'rate(process_cpu_usage[5m])' or 'jvm_memory_used_bytes{area=\"heap\"}'")
    time_range: str = Field(default="1h", description="Time range for range queries: '15m', '1h', '6h', '24h', '7d'")


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
        "Execute a PromQL query against Prometheus and return time-series results. "
        "REQUIRES valid PromQL syntax - do NOT pass natural language. "
        "You MUST call prometheus_metric_discovery first to find the correct metric names, "
        "then construct PromQL using those exact names."
    )
    args_schema: Type[BaseModel] = PrometheusQueryInput
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, promql: str, time_range: str = "1h") -> str:
        """Execute a PromQL query against Prometheus."""
        try:
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

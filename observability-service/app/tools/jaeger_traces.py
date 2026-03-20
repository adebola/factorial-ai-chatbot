"""
Jaeger/Tempo trace search tool.
"""
import logging
from typing import Type, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import BackendConfig

logger = logging.getLogger(__name__)


class JaegerTracesInput(BaseModel):
    """Input for Jaeger traces tool."""
    service: str = Field(description="Service name to search traces for")
    operation: Optional[str] = Field(default=None, description="Operation/endpoint name to filter by")
    min_duration: Optional[str] = Field(default=None, description="Minimum trace duration, e.g. '100ms', '1s', '5s'")
    time_range: str = Field(default="1h", description="Time range to search, e.g. '15m', '1h', '6h'")


def _duration_to_microseconds(duration: str) -> int:
    """Convert duration string to microseconds."""
    if duration.endswith("ms"):
        return int(float(duration[:-2]) * 1000)
    elif duration.endswith("s"):
        return int(float(duration[:-1]) * 1_000_000)
    elif duration.endswith("m"):
        return int(float(duration[:-1]) * 60_000_000)
    return int(duration)


def _microseconds_to_human(us: int) -> str:
    """Convert microseconds to human-readable duration."""
    if us >= 1_000_000:
        return f"{us / 1_000_000:.2f}s"
    elif us >= 1000:
        return f"{us / 1000:.1f}ms"
    return f"{us}us"


class JaegerTracesTool(BaseTool):
    """Search distributed traces in Jaeger or Tempo.

    Use this to find slow requests, trace errors through microservices,
    and identify bottleneck spans.
    """
    name: str = "jaeger_traces"
    description: str = (
        "Search distributed traces in Jaeger/Tempo. Use this to find slow requests, "
        "trace errors across microservices, identify bottleneck spans, and analyze "
        "request flow through the system."
    )
    args_schema: Type[BaseModel] = JaegerTracesInput
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, service: str, operation: str = None,
             min_duration: str = None, time_range: str = "1h") -> str:
        """Search for traces in Jaeger/Tempo."""
        try:
            # Try Jaeger API first, then Tempo
            result = self._query_jaeger(service, operation, min_duration, time_range)
            if result:
                return result

            result = self._query_tempo(service, operation, min_duration, time_range)
            if result:
                return result

            return f"No traces found for service '{service}' in the last {time_range}"

        except httpx.TimeoutException:
            return f"Trace search timed out after {self.config.timeout_seconds}s"
        except httpx.ConnectError as e:
            return f"Cannot connect to tracing backend at {self.config.url}: {e}"
        except Exception as e:
            return f"Trace search error: {str(e)}"

    def _query_jaeger(self, service: str, operation: str,
                      min_duration: str, time_range: str) -> Optional[str]:
        """Query Jaeger API for traces."""
        params = {
            "service": service,
            "limit": 20,
            "lookback": time_range
        }
        if operation:
            params["operation"] = operation
        if min_duration:
            params["minDuration"] = min_duration

        try:
            response = httpx.get(
                f"{self.config.url}/api/traces",
                params=params,
                headers=self.config.get_headers(),
                verify=self.config.verify_ssl,
                timeout=self.config.timeout_seconds,
                auth=self.config.get_auth_tuple()
            )

            if response.status_code != 200:
                return None

            data = response.json()
            traces = data.get("data", [])
            if not traces:
                return None

            return self._format_jaeger_traces(traces, service, time_range)

        except Exception:
            return None

    def _query_tempo(self, service: str, operation: str,
                     min_duration: str, time_range: str) -> Optional[str]:
        """Query Tempo API for traces."""
        query_parts = [f'resource.service.name="{service}"']
        if operation:
            query_parts.append(f'name="{operation}"')
        if min_duration:
            query_parts.append(f'duration>{min_duration}')

        params = {
            "q": " && ".join(query_parts),
            "limit": 20
        }

        try:
            response = httpx.get(
                f"{self.config.url}/api/search",
                params=params,
                headers=self.config.get_headers(),
                verify=self.config.verify_ssl,
                timeout=self.config.timeout_seconds,
                auth=self.config.get_auth_tuple()
            )

            if response.status_code != 200:
                return None

            data = response.json()
            traces = data.get("traces", [])
            if not traces:
                return None

            return self._format_tempo_traces(traces, service, time_range)

        except Exception:
            return None

    def _format_jaeger_traces(self, traces: list, service: str, time_range: str) -> str:
        """Format Jaeger trace results."""
        output_lines = [f"Traces for service '{service}' (last {time_range}, {len(traces)} traces):"]

        for i, trace in enumerate(traces[:20]):
            trace_id = trace.get("traceID", "unknown")
            spans = trace.get("spans", [])
            processes = trace.get("processes", {})

            if not spans:
                continue

            # Find root span
            root_span = spans[0]
            for span in spans:
                if not span.get("references"):
                    root_span = span
                    break

            duration_us = root_span.get("duration", 0)
            operation_name = root_span.get("operationName", "unknown")
            start_time = root_span.get("startTime", 0)

            # Check for errors
            has_error = any(
                tag.get("key") == "error" and tag.get("value") == True
                for span in spans
                for tag in span.get("tags", [])
            )

            # Count unique services
            service_names = set()
            for span in spans:
                pid = span.get("processID", "")
                process = processes.get(pid, {})
                service_names.add(process.get("serviceName", "unknown"))

            status = "ERROR" if has_error else "OK"
            output_lines.append(
                f"  [{i+1}] trace_id={trace_id[:16]}... "
                f"duration={_microseconds_to_human(duration_us)} "
                f"spans={len(spans)} services={len(service_names)} "
                f"status={status}"
            )
            output_lines.append(f"       root: {operation_name}")

            # Show error spans
            if has_error:
                for span in spans:
                    error_tags = [t for t in span.get("tags", []) if t.get("key") == "error" and t.get("value")]
                    if error_tags:
                        pid = span.get("processID", "")
                        svc = processes.get(pid, {}).get("serviceName", "")
                        output_lines.append(
                            f"       ERROR in {svc}/{span.get('operationName', '')}: "
                            f"duration={_microseconds_to_human(span.get('duration', 0))}"
                        )

            # Show slowest spans
            sorted_spans = sorted(spans, key=lambda s: s.get("duration", 0), reverse=True)
            for span in sorted_spans[:3]:
                pid = span.get("processID", "")
                svc = processes.get(pid, {}).get("serviceName", "")
                output_lines.append(
                    f"       slowest: {svc}/{span.get('operationName', '')} "
                    f"= {_microseconds_to_human(span.get('duration', 0))}"
                )

        return "\n".join(output_lines)

    def _format_tempo_traces(self, traces: list, service: str, time_range: str) -> str:
        """Format Tempo trace results."""
        output_lines = [f"Traces for service '{service}' (last {time_range}, {len(traces)} traces):"]

        for i, trace in enumerate(traces[:20]):
            trace_id = trace.get("traceID", "unknown")
            root_service = trace.get("rootServiceName", "unknown")
            root_name = trace.get("rootTraceName", "unknown")
            duration_ms = trace.get("durationMs", 0)
            span_count = trace.get("spanCount", 0) or trace.get("spanSets", [{}])[0].get("spans", 0) if trace.get("spanSets") else 0
            start_time = trace.get("startTimeUnixNano", "")

            output_lines.append(
                f"  [{i+1}] trace_id={trace_id[:16]}... "
                f"duration={duration_ms}ms spans={span_count} "
                f"root={root_service}/{root_name}"
            )

        return "\n".join(output_lines)

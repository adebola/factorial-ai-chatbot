"""
OpenTelemetry Collector metrics tool - scrapes collector health metrics.
"""
import logging
from typing import Type, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import BackendConfig

logger = logging.getLogger(__name__)


class OtelMetricsInput(BaseModel):
    """Input for OTel metrics tool."""
    metric_name: Optional[str] = Field(default=None, description="Specific metric name to query, e.g. 'otelcol_exporter_sent_spans_total'")
    service: Optional[str] = Field(default=None, description="Filter metrics by service or exporter name")


class OtelMetricsTool(BaseTool):
    """Check OpenTelemetry Collector health metrics.

    Use this to monitor the collector's processing pipeline health,
    including dropped spans, queue depth, and export errors.
    """
    name: str = "otel_metrics"
    description: str = (
        "Check OpenTelemetry Collector health and pipeline metrics. "
        "Use this to see if the collector is dropping spans, has queue buildup, "
        "or export errors that might indicate telemetry data loss."
    )
    args_schema: Type[BaseModel] = OtelMetricsInput
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, metric_name: str = None, service: str = None) -> str:
        """Scrape OTel collector metrics."""
        try:
            # OTel collector exposes Prometheus-compatible metrics
            metrics_path = "/metrics"
            response = httpx.get(
                f"{self.config.url}{metrics_path}",
                headers=self.config.get_headers(),
                verify=self.config.verify_ssl,
                timeout=self.config.timeout_seconds,
                auth=self.config.get_auth_tuple()
            )

            if response.status_code != 200:
                return f"OTel collector metrics endpoint returned status {response.status_code}"

            text = response.text
            lines = text.strip().split("\n")

            # Key metrics to extract
            key_metrics = {
                "otelcol_exporter_sent_spans_total": "Exported spans",
                "otelcol_exporter_send_failed_spans_total": "Failed span exports",
                "otelcol_exporter_sent_metric_points_total": "Exported metric points",
                "otelcol_exporter_send_failed_metric_points_total": "Failed metric exports",
                "otelcol_exporter_sent_log_records_total": "Exported log records",
                "otelcol_exporter_send_failed_log_records_total": "Failed log exports",
                "otelcol_receiver_accepted_spans_total": "Received spans",
                "otelcol_receiver_refused_spans_total": "Refused spans",
                "otelcol_receiver_accepted_metric_points_total": "Received metrics",
                "otelcol_processor_dropped_spans_total": "Dropped spans",
                "otelcol_processor_dropped_metric_points_total": "Dropped metrics",
                "otelcol_exporter_queue_size": "Export queue size",
                "otelcol_exporter_queue_capacity": "Export queue capacity",
                "process_runtime_total_alloc_bytes_total": "Collector memory allocated",
                "otelcol_process_uptime": "Collector uptime",
            }

            # Parse metrics
            parsed = {}
            for line in lines:
                if line.startswith("#"):
                    continue
                if not line.strip():
                    continue

                # Filter by metric name if specified
                if metric_name and not line.startswith(metric_name):
                    continue

                # Filter by service/exporter if specified
                if service and service not in line:
                    continue

                # Parse metric line: metric_name{labels} value
                try:
                    if "{" in line:
                        name_part = line[:line.index("{")]
                        rest = line[line.index("}")+ 1:].strip()
                        labels = line[line.index("{"):line.index("}") + 1]
                    else:
                        parts = line.split()
                        name_part = parts[0]
                        rest = parts[1] if len(parts) > 1 else "0"
                        labels = ""

                    value = rest.split()[0] if rest else "0"

                    if name_part in key_metrics or metric_name:
                        if name_part not in parsed:
                            parsed[name_part] = []
                        parsed[name_part].append({
                            "labels": labels,
                            "value": value
                        })
                except Exception:
                    continue

            if not parsed:
                if metric_name:
                    return f"Metric '{metric_name}' not found in OTel collector metrics"
                return "OTel collector is reachable but no key metrics found. The collector may be using non-standard metric names."

            # Format output
            output_lines = ["OTel Collector Health Metrics:"]

            # Group by health categories
            health_issues = []
            for name, entries in parsed.items():
                label = key_metrics.get(name, name)
                for entry in entries:
                    val = entry["value"]
                    labels = entry["labels"]

                    line = f"  {label}: {val}"
                    if labels:
                        line += f" {labels}"
                    output_lines.append(line)

                    # Flag potential issues
                    try:
                        numeric_val = float(val)
                        if "failed" in name and numeric_val > 0:
                            health_issues.append(f"  - {label}: {val} failures detected")
                        if "dropped" in name and numeric_val > 0:
                            health_issues.append(f"  - {label}: {val} dropped")
                        if "refused" in name and numeric_val > 0:
                            health_issues.append(f"  - {label}: {val} refused")
                        if "queue_size" in name:
                            # Check if queue is near capacity
                            capacity_entries = parsed.get(name.replace("queue_size", "queue_capacity"), [])
                            if capacity_entries:
                                try:
                                    capacity = float(capacity_entries[0]["value"])
                                    if capacity > 0 and numeric_val / capacity > 0.8:
                                        health_issues.append(
                                            f"  - Export queue near capacity: {val}/{capacity_entries[0]['value']} ({numeric_val/capacity*100:.0f}%)"
                                        )
                                except (ValueError, ZeroDivisionError):
                                    pass
                    except ValueError:
                        pass

            if health_issues:
                output_lines.append("\nPotential Issues:")
                output_lines.extend(health_issues)
            else:
                output_lines.append("\nNo health issues detected.")

            return "\n".join(output_lines)

        except httpx.TimeoutException:
            return f"OTel collector metrics request timed out after {self.config.timeout_seconds}s"
        except httpx.ConnectError as e:
            return f"Cannot connect to OTel collector at {self.config.url}: {e}"
        except Exception as e:
            return f"OTel metrics error: {str(e)}"

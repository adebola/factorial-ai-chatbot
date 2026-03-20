"""
Prometheus AlertManager tool - fetches active and pending alerts.
"""
import logging
from typing import Type, Optional

import httpx
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import BackendConfig

logger = logging.getLogger(__name__)


class PrometheusAlertsInput(BaseModel):
    """Input for Prometheus alerts tool."""
    filter: Optional[str] = Field(default=None, description="Filter alerts by label match, e.g. 'service=payments' or 'severity=critical'")
    severity: Optional[str] = Field(default=None, description="Filter by severity level: 'critical', 'warning', or 'info'")


class PrometheusAlertsTool(BaseTool):
    """Fetch active and pending alerts from AlertManager.

    Use this to check what alerts are currently firing, their severity,
    and related annotations.
    """
    name: str = "prometheus_alerts"
    description: str = (
        "Fetch active and pending alerts from Prometheus AlertManager. "
        "Use this to see what alarms are firing, their severity, and details. "
        "You can filter by service name or severity level."
    )
    args_schema: Type[BaseModel] = PrometheusAlertsInput
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, filter: str = None, severity: str = None) -> str:
        """Fetch alerts from AlertManager."""
        try:
            params = {}
            if filter:
                params["filter"] = filter

            response = httpx.get(
                f"{self.config.url}/api/v1/alerts",
                params=params,
                headers=self.config.get_headers(),
                verify=self.config.verify_ssl,
                timeout=self.config.timeout_seconds,
                auth=self.config.get_auth_tuple()
            )

            if response.status_code != 200:
                return f"AlertManager returned status {response.status_code}: {response.text[:500]}"

            data = response.json()
            alerts = data.get("data", data) if isinstance(data, dict) else data

            # Handle both AlertManager v1 and v2 response formats
            if isinstance(alerts, dict):
                alerts = alerts.get("alerts", alerts.get("data", []))
            if not isinstance(alerts, list):
                alerts = [alerts]

            # Filter by severity if specified
            if severity:
                alerts = [
                    a for a in alerts
                    if a.get("labels", {}).get("severity", "").lower() == severity.lower()
                ]

            if not alerts:
                filter_desc = f" matching filter='{filter}'" if filter else ""
                severity_desc = f" with severity='{severity}'" if severity else ""
                return f"No active alerts{filter_desc}{severity_desc}"

            output_lines = [f"Active Alerts ({len(alerts)} total):"]
            for i, alert in enumerate(alerts[:30]):
                labels = alert.get("labels", {})
                annotations = alert.get("annotations", {})
                state = alert.get("state", alert.get("status", {}).get("state", "unknown"))
                active_at = alert.get("activeAt", alert.get("startsAt", "unknown"))

                name = labels.get("alertname", "unnamed")
                sev = labels.get("severity", "unknown")
                service = labels.get("service", labels.get("job", labels.get("namespace", "")))
                summary = annotations.get("summary", annotations.get("description", ""))

                output_lines.append(
                    f"  [{i+1}] {name} (severity={sev}, state={state})"
                )
                if service:
                    output_lines.append(f"       service: {service}")
                if summary:
                    output_lines.append(f"       summary: {summary[:200]}")
                output_lines.append(f"       active_since: {active_at}")

                # Show relevant labels
                extra_labels = {k: v for k, v in labels.items()
                               if k not in ("alertname", "severity", "service", "job", "namespace", "__name__")}
                if extra_labels:
                    labels_str = ", ".join(f"{k}={v}" for k, v in list(extra_labels.items())[:5])
                    output_lines.append(f"       labels: {labels_str}")

            if len(alerts) > 30:
                output_lines.append(f"  ... and {len(alerts) - 30} more alerts")

            return "\n".join(output_lines)

        except httpx.TimeoutException:
            return f"AlertManager query timed out after {self.config.timeout_seconds}s"
        except httpx.ConnectError as e:
            return f"Cannot connect to AlertManager at {self.config.url}: {e}"
        except Exception as e:
            return f"AlertManager query error: {str(e)}"

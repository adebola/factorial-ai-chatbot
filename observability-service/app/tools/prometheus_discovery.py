"""
Prometheus metric discovery tool - discovers available metrics and their metadata.
"""
import time
import logging
from typing import Type, Optional, Dict, Any, Tuple

import httpx
from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import BackendConfig

logger = logging.getLogger(__name__)

# Module-level cache: {url: (timestamp, metric_names, metadata)}
_discovery_cache: Dict[str, Tuple[float, list, dict]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes

# Category keywords for grouping metrics
CATEGORY_KEYWORDS = {
    "cpu": ["cpu"],
    "memory": ["memory", "mem", "heap", "nonheap", "buffer"],
    "jvm": ["jvm", "java", "gc", "classloader", "threads"],
    "http": ["http", "request", "response", "servlet", "tomcat", "undertow"],
    "disk": ["disk", "filesystem", "fs", "storage"],
    "database": ["db", "jdbc", "hikari", "hikaricp", "pool", "datasource"],
    "network": ["network", "net", "tcp", "socket", "connection"],
    "process": ["process", "pid", "uptime", "start_time"],
    "system": ["system", "os", "load"],
    "cache": ["cache", "redis", "memcache"],
    "logging": ["log", "logback"],
}


class PrometheusDiscoveryInput(BaseModel):
    """Input for Prometheus metric discovery tool."""
    category: Optional[str] = Field(
        default=None,
        description=(
            "Optional category filter: 'cpu', 'memory', 'jvm', 'http', 'disk', "
            "'network', 'process', 'system', 'database', 'cache', or None to list all categories"
        )
    )
    name_pattern: Optional[str] = Field(
        default=None,
        description="Optional substring to filter metric names, e.g. 'jvm_memory' or 'process_cpu'"
    )
    metric_name: Optional[str] = Field(
        default=None,
        description=(
            "When set, discover the available labels and their values for this specific metric. "
            "Use this to find the correct label filters BEFORE querying. "
            "Example: metric_name='process_cpu_usage' returns labels like {application='order-service', instance='10.0.0.1:8080'}"
        )
    )


def _categorize_metric(name: str) -> str:
    """Assign a metric name to a category based on keywords."""
    name_lower = name.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in name_lower for kw in keywords):
            return category
    return "other"


def _get_cached(url: str) -> Optional[Tuple[list, dict]]:
    """Get cached discovery data if still valid."""
    if url in _discovery_cache:
        ts, names, metadata = _discovery_cache[url]
        if time.time() - ts < CACHE_TTL_SECONDS:
            return names, metadata
    return None


def _set_cache(url: str, names: list, metadata: dict):
    """Store discovery data in cache."""
    _discovery_cache[url] = (time.time(), names, metadata)


class PrometheusMetricDiscoveryTool(BaseTool):
    """Discover available Prometheus metrics and their types.

    Use this tool to find out what metrics are available in Prometheus before
    constructing PromQL queries. Returns metric names grouped by category
    with type information (counter, gauge, histogram, summary).
    """
    name: str = "prometheus_metric_discovery"
    description: str = (
        "Discover available Prometheus metrics and their labels. Two modes:\n"
        "1. List metrics: find available metric names by category or name_pattern.\n"
        "2. Label discovery: set metric_name to get available label keys and values for a "
        "specific metric. ALWAYS use this to find correct label filters (e.g. application, "
        "job, instance) BEFORE constructing PromQL with label filters."
    )
    args_schema: Type[BaseModel] = PrometheusDiscoveryInput
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _run(self, category: Optional[str] = None, name_pattern: Optional[str] = None,
             metric_name: Optional[str] = None) -> str:
        """Discover available metrics or labels for a specific metric."""
        try:
            # Mode 2: Label discovery for a specific metric
            if metric_name:
                return self._discover_labels(metric_name)
            # Check cache first
            cached = _get_cached(self.config.url)
            if cached:
                metric_names, metadata = cached
                logger.debug(f"Using cached discovery data ({len(metric_names)} metrics)")
            else:
                metric_names, metadata = self._fetch_discovery_data()
                _set_cache(self.config.url, metric_names, metadata)

            # Apply name_pattern filter
            if name_pattern:
                pattern_lower = name_pattern.lower()
                metric_names = [n for n in metric_names if pattern_lower in n.lower()]

            # Group by category
            grouped: Dict[str, list] = {}
            for name in metric_names:
                cat = _categorize_metric(name)
                if category and cat != category.lower():
                    continue
                grouped.setdefault(cat, []).append(name)

            if not grouped:
                filters = []
                if category:
                    filters.append(f"category='{category}'")
                if name_pattern:
                    filters.append(f"pattern='{name_pattern}'")
                filter_str = ", ".join(filters) if filters else "none"
                return f"No metrics found matching filters ({filter_str}). Try without filters or a different category."

            # Format output
            output_lines = []
            total_shown = 0
            max_total = 200

            for cat in sorted(grouped.keys()):
                metrics = sorted(grouped[cat])
                output_lines.append(f"\n## {cat.upper()} ({len(metrics)} metrics)")

                for m in metrics:
                    if total_shown >= max_total:
                        remaining = sum(len(v) for v in grouped.values()) - total_shown
                        output_lines.append(f"\n... and {remaining} more metrics (use category or name_pattern to filter)")
                        return "\n".join(output_lines)

                    meta = metadata.get(m, {})
                    type_str = meta.get("type", "")
                    help_str = meta.get("help", "")
                    suffix = ""
                    if type_str:
                        suffix += f" [{type_str}]"
                    if help_str:
                        suffix += f" - {help_str[:80]}"
                    output_lines.append(f"  {m}{suffix}")
                    total_shown += 1

            header = f"Available metrics: {sum(len(v) for v in grouped.values())} found"
            return header + "\n".join(output_lines)

        except httpx.TimeoutException:
            return f"Prometheus discovery timed out after {self.config.timeout_seconds}s"
        except httpx.ConnectError as e:
            return f"Cannot connect to Prometheus at {self.config.url}: {e}"
        except Exception as e:
            return f"Prometheus discovery error: {str(e)}"

    def _fetch_discovery_data(self) -> Tuple[list, dict]:
        """Fetch metric names and metadata from Prometheus."""
        # Get all metric names
        response = httpx.get(
            f"{self.config.url}/api/v1/label/__name__/values",
            headers=self.config.get_headers(),
            verify=self.config.verify_ssl,
            timeout=self.config.timeout_seconds,
            auth=self.config.get_auth_tuple()
        )

        if response.status_code != 200:
            raise RuntimeError(f"Failed to fetch metric names (status {response.status_code}): {response.text[:300]}")

        data = response.json()
        if data.get("status") != "success":
            raise RuntimeError(f"Prometheus error: {data.get('error', 'Unknown')}")

        metric_names = data.get("data", [])

        # Try to get metadata (types and help text)
        metadata: Dict[str, Dict[str, str]] = {}
        try:
            meta_response = httpx.get(
                f"{self.config.url}/api/v1/targets/metadata",
                headers=self.config.get_headers(),
                verify=self.config.verify_ssl,
                timeout=self.config.timeout_seconds,
                auth=self.config.get_auth_tuple()
            )
            if meta_response.status_code == 200:
                meta_data = meta_response.json()
                for target_metrics in meta_data.get("data", {}).values():
                    if isinstance(target_metrics, list):
                        for entry in target_metrics:
                            name = entry.get("metric", "")
                            if name and name not in metadata:
                                metadata[name] = {
                                    "type": entry.get("type", ""),
                                    "help": entry.get("help", ""),
                                }
        except Exception as e:
            logger.debug(f"Could not fetch metric metadata (non-fatal): {e}")

        logger.info(f"Discovered {len(metric_names)} metrics, {len(metadata)} with metadata")
        return metric_names, metadata

    def _discover_labels(self, metric_name: str) -> str:
        """Discover available labels and their values for a specific metric.

        Uses /api/v1/series to find all label combinations for the metric.
        """
        response = httpx.get(
            f"{self.config.url}/api/v1/series",
            params={"match[]": metric_name},
            headers=self.config.get_headers(),
            verify=self.config.verify_ssl,
            timeout=self.config.timeout_seconds,
            auth=self.config.get_auth_tuple()
        )

        if response.status_code != 200:
            return f"Failed to query series for '{metric_name}' (status {response.status_code}): {response.text[:300]}"

        data = response.json()
        if data.get("status") != "success":
            return f"Prometheus error: {data.get('error', 'Unknown')}"

        series = data.get("data", [])
        if not series:
            return f"No series found for metric '{metric_name}'. Check the metric name with category or name_pattern search first."

        # Collect all label keys and their unique values
        label_values: Dict[str, set] = {}
        for s in series:
            for key, value in s.items():
                if key == "__name__":
                    continue
                label_values.setdefault(key, set()).add(value)

        # Format output
        output_lines = [
            f"Labels for metric '{metric_name}' ({len(series)} series found):",
            ""
        ]
        for key in sorted(label_values.keys()):
            values = sorted(label_values[key])
            if len(values) <= 10:
                values_str = ", ".join(f'"{v}"' for v in values)
            else:
                values_str = ", ".join(f'"{v}"' for v in values[:10]) + f" ... and {len(values) - 10} more"
            output_lines.append(f"  {key}: {values_str}")

        output_lines.append("")
        output_lines.append("Example PromQL with filters:")
        # Build an example using the first series
        first_series = series[0]
        example_filters = []
        for key, value in first_series.items():
            if key != "__name__":
                example_filters.append(f'{key}="{value}"')
        if example_filters:
            output_lines.append(f"  {metric_name}{{{', '.join(example_filters[:3])}}}")

        return "\n".join(output_lines)

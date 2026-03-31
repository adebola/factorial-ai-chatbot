"""Tests for the Prometheus metric discovery tool."""
import time
import pytest
from unittest.mock import patch, MagicMock

from app.tools.prometheus_discovery import (
    PrometheusMetricDiscoveryTool,
    _discovery_cache,
    _categorize_metric,
    CACHE_TTL_SECONDS,
)
from app.tools.base import BackendConfig


@pytest.fixture
def discovery_tool():
    config = BackendConfig(
        url="http://prometheus:9090",
        auth_type="none",
        verify_ssl=False,
        timeout_seconds=5.0
    )
    return PrometheusMetricDiscoveryTool(config=config)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the discovery cache before each test."""
    _discovery_cache.clear()
    yield
    _discovery_cache.clear()


SAMPLE_METRIC_NAMES = [
    "process_cpu_usage",
    "system_cpu_usage",
    "system_cpu_count",
    "jvm_memory_used_bytes",
    "jvm_memory_committed_bytes",
    "jvm_memory_max_bytes",
    "jvm_gc_pause_seconds_count",
    "jvm_threads_live_threads",
    "http_server_requests_seconds_count",
    "http_server_requests_seconds_sum",
    "hikaricp_connections_active",
    "logback_events_total",
    "up",
]

SAMPLE_METADATA = {
    "target1": [
        {"metric": "process_cpu_usage", "type": "gauge", "help": "The recent cpu usage for the JVM process"},
        {"metric": "system_cpu_usage", "type": "gauge", "help": "The recent cpu usage for the whole system"},
        {"metric": "jvm_memory_used_bytes", "type": "gauge", "help": "The amount of used memory"},
    ]
}


def _mock_label_response():
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"status": "success", "data": SAMPLE_METRIC_NAMES}
    return mock


def _mock_metadata_response():
    mock = MagicMock()
    mock.status_code = 200
    mock.json.return_value = {"status": "success", "data": SAMPLE_METADATA}
    return mock


class TestCategorizeMetric:
    def test_cpu_metric(self):
        assert _categorize_metric("process_cpu_usage") == "cpu"
        assert _categorize_metric("system_cpu_usage") == "cpu"

    def test_memory_metric(self):
        assert _categorize_metric("jvm_memory_used_bytes") == "memory"

    def test_jvm_metric(self):
        assert _categorize_metric("jvm_gc_pause_seconds_count") == "jvm"
        assert _categorize_metric("jvm_threads_live_threads") == "jvm"

    def test_http_metric(self):
        assert _categorize_metric("http_server_requests_seconds_count") == "http"

    def test_database_metric(self):
        assert _categorize_metric("hikaricp_connections_active") == "database"

    def test_other_metric(self):
        assert _categorize_metric("up") == "other"


class TestDiscoveryExecution:
    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_successful_discovery(self, mock_get, discovery_tool):
        mock_get.side_effect = [_mock_label_response(), _mock_metadata_response()]

        result = discovery_tool._run()
        assert "process_cpu_usage" in result
        assert "jvm_memory_used_bytes" in result
        assert "CPU" in result
        assert "MEMORY" in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_category_filter(self, mock_get, discovery_tool):
        mock_get.side_effect = [_mock_label_response(), _mock_metadata_response()]

        result = discovery_tool._run(category="cpu")
        assert "process_cpu_usage" in result
        assert "system_cpu_usage" in result
        # Memory metrics should not appear
        assert "jvm_memory_used_bytes" not in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_name_pattern_filter(self, mock_get, discovery_tool):
        mock_get.side_effect = [_mock_label_response(), _mock_metadata_response()]

        result = discovery_tool._run(name_pattern="jvm_memory")
        assert "jvm_memory_used_bytes" in result
        assert "jvm_memory_committed_bytes" in result
        # Non-matching metrics should not appear
        assert "process_cpu_usage" not in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_no_matching_metrics(self, mock_get, discovery_tool):
        mock_get.side_effect = [_mock_label_response(), _mock_metadata_response()]

        result = discovery_tool._run(name_pattern="nonexistent_xyz")
        assert "No metrics found" in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_metadata_included(self, mock_get, discovery_tool):
        mock_get.side_effect = [_mock_label_response(), _mock_metadata_response()]

        result = discovery_tool._run(category="cpu")
        assert "[gauge]" in result
        assert "recent cpu usage" in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_metadata_fetch_failure_non_fatal(self, mock_get, discovery_tool):
        """Metadata failure should not prevent metric discovery."""
        label_resp = _mock_label_response()
        meta_resp = MagicMock()
        meta_resp.status_code = 404
        mock_get.side_effect = [label_resp, meta_resp]

        result = discovery_tool._run()
        # Should still return metrics, just without type/help info
        assert "process_cpu_usage" in result


class TestDiscoveryCache:
    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_cache_hit(self, mock_get, discovery_tool):
        mock_get.side_effect = [_mock_label_response(), _mock_metadata_response()]

        # First call fetches from Prometheus
        discovery_tool._run()
        assert mock_get.call_count == 2

        # Second call should use cache
        discovery_tool._run()
        assert mock_get.call_count == 2  # No additional HTTP calls

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_cache_expiry(self, mock_get, discovery_tool):
        mock_get.side_effect = [
            _mock_label_response(), _mock_metadata_response(),
            _mock_label_response(), _mock_metadata_response(),
        ]

        # First call
        discovery_tool._run()
        assert mock_get.call_count == 2

        # Expire the cache
        url = discovery_tool.config.url
        ts, names, metadata = _discovery_cache[url]
        _discovery_cache[url] = (ts - CACHE_TTL_SECONDS - 1, names, metadata)

        # Second call should re-fetch
        discovery_tool._run()
        assert mock_get.call_count == 4


class TestLabelDiscovery:
    """Tests for metric-specific label discovery (metric_name parameter)."""

    SAMPLE_SERIES = [
        {
            "__name__": "process_cpu_usage",
            "application": "order-service",
            "instance": "10.0.0.1:8080",
            "job": "spring-boot",
        },
        {
            "__name__": "process_cpu_usage",
            "application": "payment-service",
            "instance": "10.0.0.2:8080",
            "job": "spring-boot",
        },
    ]

    def _mock_series_response(self):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"status": "success", "data": self.SAMPLE_SERIES}
        return mock

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_label_discovery_returns_labels(self, mock_get, discovery_tool):
        mock_get.return_value = self._mock_series_response()

        result = discovery_tool._run(metric_name="process_cpu_usage")
        assert "application" in result
        assert "order-service" in result
        assert "payment-service" in result
        assert "instance" in result
        assert "job" in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_label_discovery_shows_example_promql(self, mock_get, discovery_tool):
        mock_get.return_value = self._mock_series_response()

        result = discovery_tool._run(metric_name="process_cpu_usage")
        assert "Example PromQL" in result
        assert "process_cpu_usage{" in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_label_discovery_correct_api_call(self, mock_get, discovery_tool):
        mock_get.return_value = self._mock_series_response()

        discovery_tool._run(metric_name="process_cpu_usage")
        call_args = mock_get.call_args
        assert "/api/v1/series" in call_args[0][0]
        assert call_args[1]["params"]["match[]"] == "process_cpu_usage"

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_label_discovery_no_series_found(self, mock_get, discovery_tool):
        mock = MagicMock()
        mock.status_code = 200
        mock.json.return_value = {"status": "success", "data": []}
        mock_get.return_value = mock

        result = discovery_tool._run(metric_name="nonexistent_metric")
        assert "No series found" in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_label_discovery_skips_metric_list(self, mock_get, discovery_tool):
        """When metric_name is set, should NOT call label/__name__/values."""
        mock_get.return_value = self._mock_series_response()

        discovery_tool._run(metric_name="process_cpu_usage")
        # Should only make 1 call (to /api/v1/series), not 2
        assert mock_get.call_count == 1

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_label_discovery_excludes_name_label(self, mock_get, discovery_tool):
        """__name__ should not appear in label output."""
        mock_get.return_value = self._mock_series_response()

        result = discovery_tool._run(metric_name="process_cpu_usage")
        assert "__name__" not in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_label_discovery_connection_error(self, mock_get, discovery_tool):
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        result = discovery_tool._run(metric_name="process_cpu_usage")
        assert "Cannot connect" in result


class TestDiscoveryErrors:
    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_connection_error(self, mock_get, discovery_tool):
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        result = discovery_tool._run()
        assert "Cannot connect" in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_timeout_error(self, mock_get, discovery_tool):
        import httpx
        mock_get.side_effect = httpx.TimeoutException("Timed out")

        result = discovery_tool._run()
        assert "timed out" in result

    @patch("app.tools.prometheus_discovery.httpx.get")
    def test_http_error_status(self, mock_get, discovery_tool):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_get.return_value = mock_response

        result = discovery_tool._run()
        assert "error" in result.lower()

"""Tests for the Prometheus query tool."""
import pytest
from unittest.mock import patch, MagicMock
import json

from app.tools.prometheus_query import PrometheusQueryTool, _parse_time_range
from app.tools.base import BackendConfig


@pytest.fixture
def prom_tool():
    config = BackendConfig(
        url="http://prometheus:9090",
        auth_type="none",
        verify_ssl=False,
        timeout_seconds=5.0
    )
    return PrometheusQueryTool(config=config)


class TestParseTimeRange:
    def test_minutes(self):
        td = _parse_time_range("30m")
        assert td.total_seconds() == 1800

    def test_hours(self):
        td = _parse_time_range("1h")
        assert td.total_seconds() == 3600

    def test_days(self):
        td = _parse_time_range("7d")
        assert td.total_seconds() == 604800


class TestPromQLGeneration:
    def test_cpu_query(self, prom_tool):
        query = prom_tool._build_promql("CPU usage for payments service", "5m")
        assert "container_cpu_usage_seconds_total" in query
        assert "payments" in query

    def test_memory_query(self, prom_tool):
        query = prom_tool._build_promql("memory usage for payments", "1h")
        assert "container_memory_usage_bytes" in query
        assert "payments" in query

    def test_error_rate_query(self, prom_tool):
        query = prom_tool._build_promql("error rate for payments service", "1h")
        assert "http_requests_total" in query
        assert '5..' in query

    def test_latency_p99_query(self, prom_tool):
        query = prom_tool._build_promql("p99 latency for payments", "1h")
        assert "histogram_quantile" in query
        assert "0.99" in query

    def test_restart_query(self, prom_tool):
        query = prom_tool._build_promql("restarts for payments", "1h")
        assert "kube_pod_container_status_restarts_total" in query

    def test_raw_promql_passthrough(self, prom_tool):
        raw = 'rate(http_requests_total{service="api"}[5m])'
        query = prom_tool._build_promql(raw, "5m")
        assert query == raw


class TestPrometheusQueryExecution:
    @patch("app.tools.prometheus_query.httpx.get")
    def test_successful_query(self, mock_get, prom_tool):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"__name__": "up", "instance": "localhost:9090"},
                        "values": [[1616000000, "1"], [1616000015, "1"]]
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        result = prom_tool._run("up metric", "1h")
        assert "PromQL:" in result
        assert "1 series" in result

    @patch("app.tools.prometheus_query.httpx.get")
    def test_no_results(self, mock_get, prom_tool):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"result": []}
        }
        mock_get.return_value = mock_response

        result = prom_tool._run("nonexistent metric", "1h")
        assert "No results" in result

    @patch("app.tools.prometheus_query.httpx.get")
    def test_connection_error(self, mock_get, prom_tool):
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        result = prom_tool._run("cpu usage", "1h")
        assert "Cannot connect" in result

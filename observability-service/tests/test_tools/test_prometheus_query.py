"""Tests for the Prometheus query tool."""
import pytest
from unittest.mock import patch, MagicMock

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

        result = prom_tool._run(promql="up", time_range="1h")
        assert "PromQL:" in result
        assert "1 series" in result

    @patch("app.tools.prometheus_query.httpx.get")
    def test_raw_promql_passthrough(self, mock_get, prom_tool):
        """Verify the tool passes PromQL directly to Prometheus."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"__name__": "process_cpu_usage"},
                        "values": [[1616000000, "0.05"]]
                    }
                ]
            }
        }
        mock_get.return_value = mock_response

        result = prom_tool._run(promql='rate(process_cpu_usage[5m])', time_range="1h")
        assert "PromQL: rate(process_cpu_usage[5m])" in result

        # Verify the exact PromQL was sent to Prometheus
        call_args = mock_get.call_args
        assert call_args[1]["params"]["query"] == "rate(process_cpu_usage[5m])"

    @patch("app.tools.prometheus_query.httpx.get")
    def test_no_results(self, mock_get, prom_tool):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "success",
            "data": {"result": []}
        }
        mock_get.return_value = mock_response

        result = prom_tool._run(promql="nonexistent_metric", time_range="1h")
        assert "No results" in result

    @patch("app.tools.prometheus_query.httpx.get")
    def test_promql_error(self, mock_get, prom_tool):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "error",
            "error": "parse error: unexpected end of input"
        }
        mock_get.return_value = mock_response

        result = prom_tool._run(promql="rate(", time_range="1h")
        assert "PromQL error" in result

    @patch("app.tools.prometheus_query.httpx.get")
    def test_connection_error(self, mock_get, prom_tool):
        import httpx
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        result = prom_tool._run(promql="up", time_range="1h")
        assert "Cannot connect" in result

    @patch("app.tools.prometheus_query.httpx.get")
    def test_fallback_to_instant_query(self, mock_get, prom_tool):
        """When range query fails, should fall back to instant query."""
        range_response = MagicMock()
        range_response.status_code = 400

        instant_response = MagicMock()
        instant_response.status_code = 200
        instant_response.json.return_value = {
            "status": "success",
            "data": {
                "result": [
                    {
                        "metric": {"__name__": "up"},
                        "value": [1616000000, "1"]
                    }
                ]
            }
        }
        mock_get.side_effect = [range_response, instant_response]

        result = prom_tool._run(promql="up", time_range="1h")
        assert "PromQL:" in result
        assert mock_get.call_count == 2

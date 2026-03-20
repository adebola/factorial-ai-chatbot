"""Tests for the Elasticsearch search tool."""
import pytest
from unittest.mock import patch, MagicMock

from app.tools.elasticsearch_search import ElasticsearchSearchTool, _parse_time_range_ms
from app.tools.base import BackendConfig


@pytest.fixture
def es_tool():
    config = BackendConfig(
        url="http://elasticsearch:9200",
        auth_type="none",
        verify_ssl=False,
        timeout_seconds=5.0
    )
    return ElasticsearchSearchTool(config=config)


class TestParseTimeRange:
    def test_minutes(self):
        assert _parse_time_range_ms("30m") == 30 * 60 * 1000

    def test_hours(self):
        assert _parse_time_range_ms("1h") == 3600 * 1000

    def test_days(self):
        assert _parse_time_range_ms("7d") == 7 * 86400 * 1000


class TestQueryBuilding:
    def test_basic_query(self, es_tool):
        query = es_tool._build_query("connection error", "1h")
        assert query["size"] == 50
        assert "multi_match" in str(query)
        assert "connection error" in str(query)

    def test_query_with_service_filter(self, es_tool):
        query = es_tool._build_query("timeout", "1h", service="payments")
        assert "payments" in str(query)

    def test_query_with_log_level(self, es_tool):
        query = es_tool._build_query("error", "1h", log_level="ERROR")
        assert "ERROR" in str(query)


class TestElasticsearchExecution:
    @patch("app.tools.elasticsearch_search.httpx.post")
    def test_successful_search(self, mock_post, es_tool):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hits": {
                "total": {"value": 5},
                "hits": [
                    {
                        "_source": {
                            "@timestamp": "2026-03-20T10:00:00Z",
                            "message": "Connection refused to db-primary",
                            "level": "ERROR",
                            "kubernetes": {
                                "pod_name": "payments-7b4f",
                                "namespace_name": "production"
                            }
                        }
                    }
                ]
            }
        }
        mock_post.return_value = mock_response

        result = es_tool._run("connection errors", "1h")
        assert "Log Search Results" in result
        assert "Connection refused" in result

    @patch("app.tools.elasticsearch_search.httpx.post")
    def test_no_results(self, mock_post, es_tool):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "hits": {"total": {"value": 0}, "hits": []}
        }
        mock_post.return_value = mock_response

        result = es_tool._run("nonexistent error", "1h")
        # Will try multiple index patterns and eventually return no results
        assert "No log entries found" in result or "Log Search Results" in result

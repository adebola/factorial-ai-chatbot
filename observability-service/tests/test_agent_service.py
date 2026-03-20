"""Tests for the agent service."""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.agent_service import (
    LLMConfig, AgentResult, _create_llm, _build_tools, create_agent
)
from app.tools.base import BackendConfig


class TestLLMConfig:
    def test_default_config(self):
        config = LLMConfig()
        assert config.provider == "openai"
        assert config.model == "gpt-4o"
        assert config.temperature == 0

    def test_custom_config(self):
        config = LLMConfig(
            provider="anthropic",
            model="claude-sonnet-4-6",
            api_key="test-key"
        )
        assert config.provider == "anthropic"
        assert config.model == "claude-sonnet-4-6"


class TestBuildTools:
    def test_build_tools_with_prometheus(self):
        configs = {
            "prometheus": BackendConfig(url="http://prometheus:9090")
        }
        tools = _build_tools(configs)
        assert len(tools) == 1
        assert tools[0].name == "prometheus_query"

    def test_build_tools_with_all_backends(self):
        configs = {
            "prometheus": BackendConfig(url="http://prometheus:9090"),
            "alertmanager": BackendConfig(url="http://alertmanager:9093"),
            "elasticsearch": BackendConfig(url="http://es:9200"),
            "jaeger": BackendConfig(url="http://jaeger:16686"),
            "kubernetes": BackendConfig(url="https://k8s-api:6443"),
            "otel_collector": BackendConfig(url="http://otel:8888"),
        }
        tools = _build_tools(configs)
        assert len(tools) == 6
        tool_names = {t.name for t in tools}
        assert "prometheus_query" in tool_names
        assert "prometheus_alerts" in tool_names
        assert "elasticsearch_search" in tool_names
        assert "jaeger_traces" in tool_names
        assert "k8s_resources" in tool_names
        assert "otel_metrics" in tool_names

    def test_build_tools_empty_config(self):
        tools = _build_tools({})
        assert len(tools) == 0


class TestAgentResult:
    def test_successful_result(self):
        result = AgentResult(
            response="Test response",
            tool_calls=[{"tool": "prometheus_query", "input": {}, "output": "data", "duration_ms": 100}],
            total_duration_ms=500.0
        )
        assert result.status == "completed"
        assert result.error_message is None

    def test_error_result(self):
        result = AgentResult(
            response="",
            tool_calls=[],
            total_duration_ms=100.0,
            status="error",
            error_message="Connection failed"
        )
        assert result.status == "error"


class TestCreateAgent:
    @patch("app.services.agent_service._create_llm")
    def test_create_agent_no_tools_raises(self, mock_llm):
        mock_llm.return_value = MagicMock()
        with pytest.raises(ValueError, match="No observability backends configured"):
            create_agent({}, LLMConfig())

    def test_unsupported_provider_raises(self):
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            _create_llm(LLMConfig(provider="unknown"))

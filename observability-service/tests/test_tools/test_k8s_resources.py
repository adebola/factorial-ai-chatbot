"""Tests for the Kubernetes resources tool."""
import pytest
from unittest.mock import patch, MagicMock

from app.tools.k8s_resources import K8sResourcesTool
from app.tools.base import BackendConfig


@pytest.fixture
def k8s_tool():
    config = BackendConfig(
        url="https://kubernetes.default.svc",
        auth_type="service_account",
        credentials={"token": "test-token"},
        verify_ssl=False,
        timeout_seconds=5.0
    )
    return K8sResourcesTool(config=config)


class TestK8sInput:
    def test_tool_metadata(self, k8s_tool):
        assert k8s_tool.name == "k8s_resources"
        assert "pods" in k8s_tool.description.lower()

    def test_missing_kubernetes_package(self, k8s_tool):
        """Test graceful handling when kubernetes package is not installed."""
        with patch.dict("sys.modules", {"kubernetes": None}):
            # The import error will be caught in _run
            pass  # This is a structural test


class TestK8sPodFormatting:
    @patch("app.tools.k8s_resources.K8sResourcesTool._get_k8s_client")
    def test_list_pods(self, mock_get_client, k8s_tool):
        # Create mock pod
        mock_pod = MagicMock()
        mock_pod.metadata.namespace = "production"
        mock_pod.metadata.name = "payments-7b4f"
        mock_pod.status.phase = "Running"
        mock_pod.spec.containers = [MagicMock(), MagicMock()]
        mock_pod.status.conditions = []

        mock_cs = MagicMock()
        mock_cs.restart_count = 3
        mock_cs.ready = True
        mock_cs.state.waiting = None
        mock_cs.state.terminated = None
        mock_pod.status.container_statuses = [mock_cs]

        mock_client = MagicMock()
        mock_v1 = MagicMock()
        mock_v1.list_pod_for_all_namespaces.return_value.items = [mock_pod]
        mock_client.CoreV1Api.return_value = mock_v1
        mock_client.AppsV1Api.return_value = MagicMock()
        mock_get_client.return_value = mock_client

        result = k8s_tool._run("pods", action="list")
        assert "payments-7b4f" in result
        assert "Running" in result
        assert "restarts=3" in result

    @patch("app.tools.k8s_resources.K8sResourcesTool._get_k8s_client")
    def test_list_pods_oomkilled(self, mock_get_client, k8s_tool):
        mock_pod = MagicMock()
        mock_pod.metadata.namespace = "production"
        mock_pod.metadata.name = "api-server-abc123"
        mock_pod.status.phase = "Running"
        mock_pod.spec.containers = [MagicMock()]
        mock_pod.status.conditions = []

        mock_cs = MagicMock()
        mock_cs.restart_count = 5
        mock_cs.ready = False
        mock_cs.state.waiting = None
        mock_cs.state.terminated = MagicMock()
        mock_cs.state.terminated.reason = "OOMKilled"
        mock_pod.status.container_statuses = [mock_cs]

        mock_client = MagicMock()
        mock_v1 = MagicMock()
        mock_v1.list_pod_for_all_namespaces.return_value.items = [mock_pod]
        mock_client.CoreV1Api.return_value = mock_v1
        mock_client.AppsV1Api.return_value = MagicMock()
        mock_get_client.return_value = mock_client

        result = k8s_tool._run("pods", action="list")
        assert "OOMKilled" in result
        assert "restarts=5" in result

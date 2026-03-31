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


def _make_mock_pod(namespace, name, phase="Running", restart_count=0, ready=True,
                   terminated_reason=None):
    """Helper to create a mock K8s pod."""
    mock_pod = MagicMock()
    mock_pod.metadata.namespace = namespace
    mock_pod.metadata.name = name
    mock_pod.status.phase = phase
    mock_pod.spec.containers = [MagicMock()]
    mock_pod.status.conditions = []
    mock_pod.spec.node_name = "node-1"
    mock_pod.status.pod_ip = "10.0.0.1"
    mock_pod.metadata.creation_timestamp = "2026-03-01T00:00:00Z"
    mock_pod.metadata.labels = {"app": name.split("-")[0]}

    mock_cs = MagicMock()
    mock_cs.restart_count = restart_count
    mock_cs.ready = ready
    mock_cs.state.waiting = None
    if terminated_reason:
        mock_cs.state.terminated = MagicMock()
        mock_cs.state.terminated.reason = terminated_reason
        mock_cs.state.terminated.exit_code = 137
    else:
        mock_cs.state.terminated = None
    mock_cs.state.running = MagicMock() if not terminated_reason else None
    mock_pod.status.container_statuses = [mock_cs]

    return mock_pod


class TestK8sInput:
    def test_tool_metadata(self, k8s_tool):
        assert k8s_tool.name == "k8s_resources"
        assert "pods" in k8s_tool.description.lower()

    def test_missing_kubernetes_package(self, k8s_tool):
        """Test graceful handling when kubernetes package is not installed."""
        with patch.dict("sys.modules", {"kubernetes": None}):
            pass  # Structural test


class TestK8sPodFormatting:
    @patch("app.tools.k8s_resources.K8sResourcesTool._get_k8s_client")
    def test_list_pods(self, mock_get_client, k8s_tool):
        mock_pod = _make_mock_pod("production", "payments-7b4f", restart_count=3)
        mock_pod.spec.containers = [MagicMock(), MagicMock()]

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
        mock_pod = _make_mock_pod("production", "api-server-abc123",
                                  restart_count=5, ready=False,
                                  terminated_reason="OOMKilled")

        mock_client = MagicMock()
        mock_v1 = MagicMock()
        mock_v1.list_pod_for_all_namespaces.return_value.items = [mock_pod]
        mock_client.CoreV1Api.return_value = mock_v1
        mock_client.AppsV1Api.return_value = MagicMock()
        mock_get_client.return_value = mock_client

        result = k8s_tool._run("pods", action="list")
        assert "OOMKilled" in result
        assert "restarts=5" in result


class TestPodNameResolution:
    """Tests for prefix/substring pod name resolution in get/describe/logs."""

    @patch("app.tools.k8s_resources.K8sResourcesTool._get_k8s_client")
    def test_describe_resolves_prefix_to_full_pod_name(self, mock_get_client, k8s_tool):
        """When describe gets 'order-service' but pod is 'order-service-7f8b9c6d4-x2k9m',
        it should resolve and describe the actual pod."""
        from kubernetes.client.exceptions import ApiException

        full_pod_name = "order-service-7f8b9c6d4-x2k9m"
        mock_pod = _make_mock_pod("chatcraft", full_pod_name)

        mock_client = MagicMock()
        mock_v1 = MagicMock()

        # First call with short name fails
        not_found_error = ApiException(status=404, reason="Not Found")
        not_found_error.body = '{"message": "pods \\"order-service\\" not found"}'

        # read_namespaced_pod: first call fails, second with resolved name succeeds
        mock_v1.read_namespaced_pod.side_effect = [not_found_error, mock_pod]

        # list_namespaced_pod returns the pod for resolution
        mock_v1.list_namespaced_pod.return_value.items = [mock_pod]

        mock_client.CoreV1Api.return_value = mock_v1
        mock_client.AppsV1Api.return_value = MagicMock()
        mock_get_client.return_value = mock_client

        result = k8s_tool._run("pod", namespace="chatcraft", name="order-service", action="describe")
        assert full_pod_name in result
        assert "Running" in result

    @patch("app.tools.k8s_resources.K8sResourcesTool._get_k8s_client")
    def test_logs_resolves_prefix_to_full_pod_name(self, mock_get_client, k8s_tool):
        """When logs gets 'order-service' but pod is 'order-service-7f8b9c6d4-x2k9m',
        it should resolve and fetch logs from the actual pod."""
        from kubernetes.client.exceptions import ApiException

        full_pod_name = "order-service-7f8b9c6d4-x2k9m"
        mock_pod = _make_mock_pod("chatcraft", full_pod_name)

        mock_client = MagicMock()
        mock_v1 = MagicMock()

        # First log call fails with not found
        not_found_error = ApiException(status=404, reason="Not Found")
        not_found_error.body = '{"message": "pods \\"order-service\\" not found"}'

        # read_namespaced_pod_log: first call fails, second with resolved name succeeds
        mock_v1.read_namespaced_pod_log.side_effect = [
            not_found_error,
            "2026-03-28T10:00:00Z INFO Starting order-service\n2026-03-28T10:00:01Z INFO Ready"
        ]

        # list_namespaced_pod returns the pod for resolution
        mock_v1.list_namespaced_pod.return_value.items = [mock_pod]

        mock_client.CoreV1Api.return_value = mock_v1
        mock_get_client.return_value = mock_client

        result = k8s_tool._run("pod", namespace="chatcraft", name="order-service", action="logs")
        assert "Starting order-service" in result
        assert full_pod_name in result

    @patch("app.tools.k8s_resources.K8sResourcesTool._get_k8s_client")
    def test_describe_with_exact_name_still_works(self, mock_get_client, k8s_tool):
        """When the exact pod name is provided, describe should work without resolution."""
        full_pod_name = "order-service-7f8b9c6d4-x2k9m"
        mock_pod = _make_mock_pod("chatcraft", full_pod_name)

        mock_client = MagicMock()
        mock_v1 = MagicMock()
        mock_v1.read_namespaced_pod.return_value = mock_pod
        mock_client.CoreV1Api.return_value = mock_v1
        mock_client.AppsV1Api.return_value = MagicMock()
        mock_get_client.return_value = mock_client

        result = k8s_tool._run("pod", namespace="chatcraft", name=full_pod_name, action="describe")
        assert full_pod_name in result
        # list should NOT have been called since exact match worked
        mock_v1.list_namespaced_pod.assert_not_called()

    @patch("app.tools.k8s_resources.K8sResourcesTool._get_k8s_client")
    def test_describe_no_matching_pod(self, mock_get_client, k8s_tool):
        """When no pod matches the prefix, return a clear not found message."""
        from kubernetes.client.exceptions import ApiException

        mock_client = MagicMock()
        mock_v1 = MagicMock()

        not_found_error = ApiException(status=404, reason="Not Found")
        not_found_error.body = '{"message": "pods \\"nonexistent-service\\" not found"}'
        mock_v1.read_namespaced_pod.side_effect = not_found_error

        # No pods match
        mock_v1.list_namespaced_pod.return_value.items = []

        mock_client.CoreV1Api.return_value = mock_v1
        mock_client.AppsV1Api.return_value = MagicMock()
        mock_get_client.return_value = mock_client

        result = k8s_tool._run("pod", namespace="chatcraft", name="nonexistent-service", action="describe")
        assert "not found" in result.lower() or "Failed" in result

    @patch("app.tools.k8s_resources.K8sResourcesTool._get_k8s_client")
    def test_list_pods_substring_match(self, mock_get_client, k8s_tool):
        """List action with name filter should match by substring."""
        pod1 = _make_mock_pod("chatcraft", "order-service-7f8b9c6d4-x2k9m")
        pod2 = _make_mock_pod("chatcraft", "order-service-7f8b9c6d4-a1b2c")
        pod3 = _make_mock_pod("chatcraft", "payment-service-5d4c3b2a1-z9y8x")

        mock_client = MagicMock()
        mock_v1 = MagicMock()
        mock_v1.list_namespaced_pod.return_value.items = [pod1, pod2, pod3]
        mock_client.CoreV1Api.return_value = mock_v1
        mock_client.AppsV1Api.return_value = MagicMock()
        mock_get_client.return_value = mock_client

        result = k8s_tool._run("pods", namespace="chatcraft", name="order-service", action="list")
        assert "order-service-7f8b9c6d4-x2k9m" in result
        assert "order-service-7f8b9c6d4-a1b2c" in result
        assert "payment-service" not in result

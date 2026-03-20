"""
Kubernetes resources tool - queries pods, deployments, events, and logs.
"""
import os
import logging
from typing import Type, Optional

from pydantic import BaseModel, ConfigDict, Field
from langchain_core.tools import BaseTool

from .base import BackendConfig

logger = logging.getLogger(__name__)


class K8sResourcesInput(BaseModel):
    """Input for Kubernetes resources tool."""
    resource_type: str = Field(description="Type of resource: 'pods', 'deployments', 'services', 'events', 'nodes', 'statefulsets', 'jobs'")
    namespace: Optional[str] = Field(default=None, description="Kubernetes namespace to query. Leave empty for all namespaces.")
    name: Optional[str] = Field(default=None, description="Resource name or name pattern to filter by")
    action: str = Field(default="list", description="Action: 'list', 'get', 'events', 'logs', 'describe'")


class K8sResourcesTool(BaseTool):
    """Query Kubernetes cluster resources.

    Use this to check pod status, deployments, recent events,
    container logs, and resource usage.
    """
    name: str = "k8s_resources"
    description: str = (
        "Query Kubernetes cluster resources including pods, deployments, events, "
        "and container logs. Use this to check pod health, restart counts, "
        "OOMKill events, resource usage, and recent cluster events."
    )
    args_schema: Type[BaseModel] = K8sResourcesInput
    config: BackendConfig
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_k8s_client(self):
        """Get a configured Kubernetes client."""
        from kubernetes import client, config as k8s_config

        in_cluster = os.environ.get("K8S_IN_CLUSTER", "false").lower() == "true"

        if in_cluster:
            k8s_config.load_incluster_config()
        elif self.config.auth_type == "service_account" and self.config.credentials:
            # Load from service account token
            configuration = client.Configuration()
            configuration.host = self.config.url
            configuration.api_key = {
                "authorization": f"Bearer {self.config.credentials.get('token', '')}"
            }
            if not self.config.verify_ssl:
                configuration.verify_ssl = False
            client.Configuration.set_default(configuration)
        else:
            try:
                k8s_config.load_kube_config()
            except Exception:
                k8s_config.load_incluster_config()

        return client

    def _run(self, resource_type: str, namespace: str = None,
             name: str = None, action: str = "list") -> str:
        """Query Kubernetes resources."""
        try:
            k8s = self._get_k8s_client()

            match action:
                case "logs":
                    return self._get_logs(k8s, namespace, name)
                case "events":
                    return self._get_events(k8s, namespace, name)
                case "describe" | "get":
                    return self._describe_resource(k8s, resource_type, namespace, name)
                case "list" | _:
                    return self._list_resources(k8s, resource_type, namespace, name)

        except ImportError:
            return "Kubernetes Python client not installed. Install with: pip install kubernetes"
        except Exception as e:
            return f"Kubernetes query error: {str(e)}"

    def _list_resources(self, k8s, resource_type: str,
                        namespace: str = None, name: str = None) -> str:
        """List Kubernetes resources."""
        v1 = k8s.CoreV1Api()
        apps_v1 = k8s.AppsV1Api()

        match resource_type.lower():
            case "pods" | "pod":
                return self._list_pods(v1, namespace, name)
            case "deployments" | "deployment" | "deploy":
                return self._list_deployments(apps_v1, namespace, name)
            case "services" | "service" | "svc":
                return self._list_services(v1, namespace, name)
            case "nodes" | "node":
                return self._list_nodes(v1)
            case "events" | "event":
                return self._get_events(k8s, namespace, name)
            case "statefulsets" | "statefulset" | "sts":
                return self._list_statefulsets(apps_v1, namespace, name)
            case "jobs" | "job":
                batch_v1 = k8s.BatchV1Api()
                return self._list_jobs(batch_v1, namespace, name)
            case _:
                return f"Unsupported resource type: {resource_type}. Supported: pods, deployments, services, nodes, events, statefulsets, jobs"

    def _list_pods(self, v1, namespace: str = None, name: str = None) -> str:
        """List pods with status details."""
        if namespace:
            pods = v1.list_namespaced_pod(namespace=namespace)
        else:
            pods = v1.list_pod_for_all_namespaces()

        items = pods.items
        if name:
            items = [p for p in items if name.lower() in p.metadata.name.lower()]

        if not items:
            return f"No pods found{' in namespace ' + namespace if namespace else ''}{' matching ' + name if name else ''}"

        output_lines = [f"Pods ({len(items)} found):"]
        for pod in items[:30]:
            ns = pod.metadata.namespace
            pod_name = pod.metadata.name
            phase = pod.status.phase

            # Container statuses
            restarts = 0
            ready_count = 0
            total_count = len(pod.spec.containers)
            status_detail = ""

            if pod.status.container_statuses:
                for cs in pod.status.container_statuses:
                    restarts += cs.restart_count
                    if cs.ready:
                        ready_count += 1
                    if cs.state.waiting:
                        status_detail = f" ({cs.state.waiting.reason})"
                    elif cs.state.terminated:
                        status_detail = f" ({cs.state.terminated.reason})"
                        if cs.state.terminated.reason == "OOMKilled":
                            status_detail = " (OOMKilled!)"

            output_lines.append(
                f"  {ns}/{pod_name}: {phase}{status_detail} "
                f"ready={ready_count}/{total_count} restarts={restarts}"
            )

            # Show resource usage if available
            if pod.status.conditions:
                not_ready = [c for c in pod.status.conditions if c.type == "Ready" and c.status != "True"]
                if not_ready:
                    output_lines.append(f"    NOT READY: {not_ready[0].reason}: {not_ready[0].message}")

        if len(items) > 30:
            output_lines.append(f"  ... and {len(items) - 30} more pods")

        return "\n".join(output_lines)

    def _list_deployments(self, apps_v1, namespace: str = None, name: str = None) -> str:
        """List deployments with status."""
        if namespace:
            deploys = apps_v1.list_namespaced_deployment(namespace=namespace)
        else:
            deploys = apps_v1.list_deployment_for_all_namespaces()

        items = deploys.items
        if name:
            items = [d for d in items if name.lower() in d.metadata.name.lower()]

        if not items:
            return f"No deployments found{' in namespace ' + namespace if namespace else ''}"

        output_lines = [f"Deployments ({len(items)} found):"]
        for deploy in items[:30]:
            ns = deploy.metadata.namespace
            deploy_name = deploy.metadata.name
            replicas = deploy.spec.replicas or 0
            ready = deploy.status.ready_replicas or 0
            available = deploy.status.available_replicas or 0
            updated = deploy.status.updated_replicas or 0

            status = "OK" if ready == replicas else "DEGRADED"
            output_lines.append(
                f"  {ns}/{deploy_name}: {status} "
                f"ready={ready}/{replicas} available={available} updated={updated}"
            )

        return "\n".join(output_lines)

    def _list_services(self, v1, namespace: str = None, name: str = None) -> str:
        """List services."""
        if namespace:
            svcs = v1.list_namespaced_service(namespace=namespace)
        else:
            svcs = v1.list_service_for_all_namespaces()

        items = svcs.items
        if name:
            items = [s for s in items if name.lower() in s.metadata.name.lower()]

        if not items:
            return "No services found"

        output_lines = [f"Services ({len(items)} found):"]
        for svc in items[:30]:
            ns = svc.metadata.namespace
            svc_name = svc.metadata.name
            svc_type = svc.spec.type
            ports = ", ".join(f"{p.port}/{p.protocol}" for p in (svc.spec.ports or []))
            cluster_ip = svc.spec.cluster_ip or "None"
            output_lines.append(f"  {ns}/{svc_name}: type={svc_type} cluster_ip={cluster_ip} ports=[{ports}]")

        return "\n".join(output_lines)

    def _list_nodes(self, v1) -> str:
        """List cluster nodes."""
        nodes = v1.list_node()

        output_lines = [f"Nodes ({len(nodes.items)} found):"]
        for node in nodes.items:
            name = node.metadata.name
            conditions = {c.type: c.status for c in (node.status.conditions or [])}
            ready = conditions.get("Ready", "Unknown")
            memory_pressure = conditions.get("MemoryPressure", "False")
            disk_pressure = conditions.get("DiskPressure", "False")

            capacity = node.status.capacity or {}
            alloc = node.status.allocatable or {}

            output_lines.append(
                f"  {name}: Ready={ready} MemPressure={memory_pressure} DiskPressure={disk_pressure}"
            )
            output_lines.append(
                f"    capacity: cpu={capacity.get('cpu', '?')}, memory={capacity.get('memory', '?')}, pods={capacity.get('pods', '?')}"
            )

        return "\n".join(output_lines)

    def _list_statefulsets(self, apps_v1, namespace: str = None, name: str = None) -> str:
        """List statefulsets."""
        if namespace:
            sts_list = apps_v1.list_namespaced_stateful_set(namespace=namespace)
        else:
            sts_list = apps_v1.list_stateful_set_for_all_namespaces()

        items = sts_list.items
        if name:
            items = [s for s in items if name.lower() in s.metadata.name.lower()]

        if not items:
            return "No statefulsets found"

        output_lines = [f"StatefulSets ({len(items)} found):"]
        for sts in items[:20]:
            ns = sts.metadata.namespace
            sts_name = sts.metadata.name
            replicas = sts.spec.replicas or 0
            ready = sts.status.ready_replicas or 0
            output_lines.append(f"  {ns}/{sts_name}: ready={ready}/{replicas}")

        return "\n".join(output_lines)

    def _list_jobs(self, batch_v1, namespace: str = None, name: str = None) -> str:
        """List jobs."""
        if namespace:
            jobs = batch_v1.list_namespaced_job(namespace=namespace)
        else:
            jobs = batch_v1.list_job_for_all_namespaces()

        items = jobs.items
        if name:
            items = [j for j in items if name.lower() in j.metadata.name.lower()]

        if not items:
            return "No jobs found"

        output_lines = [f"Jobs ({len(items)} found):"]
        for job in items[:20]:
            ns = job.metadata.namespace
            job_name = job.metadata.name
            succeeded = job.status.succeeded or 0
            failed = job.status.failed or 0
            active = job.status.active or 0
            output_lines.append(
                f"  {ns}/{job_name}: active={active} succeeded={succeeded} failed={failed}"
            )

        return "\n".join(output_lines)

    def _get_events(self, k8s, namespace: str = None, name: str = None) -> str:
        """Get Kubernetes events."""
        v1 = k8s.CoreV1Api()

        if namespace:
            events = v1.list_namespaced_event(namespace=namespace)
        else:
            events = v1.list_event_for_all_namespaces()

        items = sorted(events.items, key=lambda e: e.last_timestamp or e.event_time or e.metadata.creation_timestamp, reverse=True)

        if name:
            items = [e for e in items if name.lower() in (e.involved_object.name or "").lower()]

        items = items[:30]

        if not items:
            return f"No events found{' in namespace ' + namespace if namespace else ''}"

        output_lines = [f"Recent Events ({len(items)} shown):"]
        for event in items:
            ts = event.last_timestamp or event.event_time or event.metadata.creation_timestamp
            etype = event.type  # Normal or Warning
            reason = event.reason
            obj_kind = event.involved_object.kind
            obj_name = event.involved_object.name
            ns = event.involved_object.namespace or ""
            message = event.message or ""
            count = event.count or 1

            marker = "WARNING" if etype == "Warning" else "Normal"
            output_lines.append(
                f"  [{marker}] {ts} {reason} {obj_kind}/{ns}/{obj_name} (x{count})"
            )
            output_lines.append(f"    {message[:200]}")

        return "\n".join(output_lines)

    def _get_logs(self, k8s, namespace: str = None, name: str = None) -> str:
        """Get pod logs."""
        if not name:
            return "Pod name is required for log retrieval"

        v1 = k8s.CoreV1Api()
        ns = namespace or "default"

        try:
            logs = v1.read_namespaced_pod_log(
                name=name,
                namespace=ns,
                tail_lines=100,
                timestamps=True
            )

            if not logs:
                return f"No logs available for pod {ns}/{name}"

            lines = logs.strip().split("\n")
            output_lines = [f"Logs for pod {ns}/{name} (last {len(lines)} lines):"]
            for line in lines[-100:]:
                output_lines.append(f"  {line}")

            return "\n".join(output_lines)

        except Exception as e:
            if "not found" in str(e).lower():
                return f"Pod {ns}/{name} not found"
            return f"Failed to get logs for {ns}/{name}: {str(e)}"

    def _describe_resource(self, k8s, resource_type: str,
                           namespace: str = None, name: str = None) -> str:
        """Describe a specific resource."""
        if not name:
            return "Resource name is required for describe"

        v1 = k8s.CoreV1Api()
        ns = namespace or "default"

        match resource_type.lower():
            case "pods" | "pod":
                try:
                    pod = v1.read_namespaced_pod(name=name, namespace=ns)
                    return self._format_pod_describe(pod)
                except Exception as e:
                    return f"Failed to describe pod {ns}/{name}: {str(e)}"
            case _:
                return self._list_resources(k8s, resource_type, namespace, name)

    def _format_pod_describe(self, pod) -> str:
        """Format detailed pod description."""
        output_lines = [
            f"Pod: {pod.metadata.namespace}/{pod.metadata.name}",
            f"  Status: {pod.status.phase}",
            f"  Node: {pod.spec.node_name}",
            f"  IP: {pod.status.pod_ip}",
            f"  Created: {pod.metadata.creation_timestamp}",
        ]

        # Labels
        if pod.metadata.labels:
            labels_str = ", ".join(f"{k}={v}" for k, v in pod.metadata.labels.items())
            output_lines.append(f"  Labels: {labels_str}")

        # Containers
        output_lines.append("  Containers:")
        for container in pod.spec.containers:
            output_lines.append(f"    - {container.name}: image={container.image}")
            if container.resources:
                requests = container.resources.requests or {}
                limits = container.resources.limits or {}
                output_lines.append(
                    f"      resources: requests(cpu={requests.get('cpu', '?')}, mem={requests.get('memory', '?')}) "
                    f"limits(cpu={limits.get('cpu', '?')}, mem={limits.get('memory', '?')})"
                )

        # Container statuses
        if pod.status.container_statuses:
            output_lines.append("  Container Statuses:")
            for cs in pod.status.container_statuses:
                state = "running" if cs.state.running else "waiting" if cs.state.waiting else "terminated"
                output_lines.append(
                    f"    - {cs.name}: {state} ready={cs.ready} restarts={cs.restart_count}"
                )
                if cs.state.waiting:
                    output_lines.append(f"      reason: {cs.state.waiting.reason}: {cs.state.waiting.message or ''}")
                if cs.state.terminated:
                    output_lines.append(
                        f"      terminated: reason={cs.state.terminated.reason} exit_code={cs.state.terminated.exit_code}"
                    )

        # Conditions
        if pod.status.conditions:
            output_lines.append("  Conditions:")
            for c in pod.status.conditions:
                output_lines.append(f"    {c.type}: {c.status} (reason={c.reason})")

        return "\n".join(output_lines)

"""
Backend configuration CRUD API.
"""
import os
import time
import logging
from typing import List

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..models.backend_config import ObservabilityBackend
from ..schemas.backend import (
    BackendCreateRequest, BackendUpdateRequest, BackendResponse, BackendTestResult
)
from ..services.dependencies import TokenClaims, validate_token_or_api_key, require_system_admin
from ..services.credential_service import credential_service

logger = logging.getLogger(__name__)
router = APIRouter()


def _test_kafka_connectivity(backend) -> BackendTestResult:
    """Test Kafka connectivity by constructing an AdminClient and calling describe_cluster.

    Mirrors `_test_k8s_connectivity` in shape because Kafka, like Kubernetes, isn't
    HTTP and can't reuse the generic httpx test branch in `test_backend`.
    Uses a short request_timeout (5s) regardless of `backend.timeout_seconds` so a
    misconfigured broker doesn't tie up the API.

    Defensively strips an http:// or https:// scheme prefix from each bootstrap
    server entry — the URL field in the admin form is labelled "URL" so users
    intuitively type http://, but kafka-python parses bootstrap_servers as plain
    host:port and would otherwise blow up with an opaque error.
    """
    logger.info("Testing Kafka connectivity to %s", backend.url)
    start_time = time.time()
    try:
        from kafka.admin import KafkaAdminClient
        from kafka.errors import NoBrokersAvailable, NodeNotReadyError, KafkaConnectionError

        if not backend.url:
            return BackendTestResult(
                backend_type="kafka",
                url=None,
                reachable=False,
                error="No bootstrap servers configured (url is empty)",
            )

        bootstrap_servers = []
        for raw in backend.url.split(","):
            s = raw.strip()
            if not s:
                continue
            # Tolerate http:// and https:// scheme prefixes that users may type
            # out of habit; kafka-python expects plain host:port.
            for prefix in ("http://", "https://"):
                if s.lower().startswith(prefix):
                    s = s[len(prefix):]
                    break
            # Trim any trailing path component (e.g. localhost:9092/ → localhost:9092)
            if "/" in s:
                s = s.split("/", 1)[0]
            bootstrap_servers.append(s)

        # Both timeouts matter. kafka-python's bootstrap handshake includes an
        # API-version negotiation gated by `api_version_auto_timeout_ms`
        # (default 2000ms), and a 2s default is too short against several
        # broker images — the bootstrap aborts with NoBrokersAvailable before
        # it ever returns metadata. We bump BOTH to 10s for the test endpoint;
        # the API stays bounded because the test never hangs longer than that.
        admin = KafkaAdminClient(
            bootstrap_servers=bootstrap_servers,
            client_id="chatcraft-observability-test",
            request_timeout_ms=10000,
            api_version_auto_timeout_ms=10000,
        )
        try:
            cluster = admin.describe_cluster()
        finally:
            try:
                admin.close()
            except Exception:
                pass

        response_time_ms = (time.time() - start_time) * 1000
        brokers = cluster.get("brokers", []) or []
        return BackendTestResult(
            backend_type="kafka",
            url=backend.url,
            reachable=True,
            response_time_ms=round(response_time_ms, 1),
            details={
                "broker_count": len(brokers),
                "controller_id": cluster.get("controller_id"),
                "cluster_id": cluster.get("cluster_id"),
                "bootstrap_servers": bootstrap_servers,
            },
        )
    except NodeNotReadyError as e:
        # Bootstrap connection succeeded but the client could not reach a broker
        # by the hostname Kafka returned in metadata — almost always the
        # advertised.listeners hostname being unresolvable from the client side
        # (e.g. an in-cluster DNS name when running outside the cluster, or a
        # port-forward + advertised.listeners mismatch).
        response_time_ms = (time.time() - start_time) * 1000
        return BackendTestResult(
            backend_type="kafka",
            url=backend.url,
            reachable=False,
            response_time_ms=round(response_time_ms, 1),
            error=(
                f"{e}. The bootstrap server is reachable but Kafka advertised a "
                "broker hostname that this client cannot resolve. This is the "
                "advertised.listeners problem: check the broker's "
                "KAFKA_ADVERTISED_LISTENERS env var. If you are running "
                "observability-service outside the cluster and port-forwarding, "
                "either add a /etc/hosts entry mapping the advertised hostname "
                "to 127.0.0.1, or expose an EXTERNAL listener on the broker "
                "advertising localhost (or the host this service runs on)."
            ),
        )
    except NoBrokersAvailable as e:
        response_time_ms = (time.time() - start_time) * 1000
        return BackendTestResult(
            backend_type="kafka",
            url=backend.url,
            reachable=False,
            response_time_ms=round(response_time_ms, 1),
            error=(
                f"No brokers available at {bootstrap_servers}. "
                "Check that the host:port is reachable from this service "
                "(port-forward up? security group / network policy open?) and "
                "that the value is plain host:port (no http:// scheme)."
            ),
        )
    except KafkaConnectionError as e:
        response_time_ms = (time.time() - start_time) * 1000
        return BackendTestResult(
            backend_type="kafka",
            url=backend.url,
            reachable=False,
            response_time_ms=round(response_time_ms, 1),
            error=f"Kafka connection error: {e}",
        )
    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        return BackendTestResult(
            backend_type="kafka",
            url=backend.url,
            reachable=False,
            response_time_ms=round(response_time_ms, 1),
            error=str(e),
        )


def _test_k8s_connectivity(backend) -> BackendTestResult:
    """Test Kubernetes cluster connectivity using the Python client.

    Uses the same auth logic as K8sResourcesTool: in-cluster → service_account → kubeconfig.
    """

    logger.info("Testing Kubernetes connectivity")

    start_time = time.time()
    try:
        from kubernetes import client, config as k8s_config

        in_cluster = os.environ.get("K8S_IN_CLUSTER", "false").lower() == "true"

        if in_cluster:
            k8s_config.load_incluster_config()
        elif backend.auth_type == "service_account" and backend.credentials_encrypted:
            creds = credential_service.decrypt(backend.credentials_encrypted)
            configuration = client.Configuration()
            configuration.host = backend.url
            configuration.api_key = {
                "authorization": f"Bearer {creds.get('token', '')}"
            }
            if not backend.verify_ssl:
                configuration.verify_ssl = False
            client.Configuration.set_default(configuration)
        else:
            try:
                k8s_config.load_kube_config()
            except Exception:
                k8s_config.load_incluster_config()

        v1 = client.CoreV1Api()
        namespaces = v1.list_namespace(timeout_seconds=10)
        ns_names = [ns.metadata.name for ns in namespaces.items]

        response_time_ms = (time.time() - start_time) * 1000

        return BackendTestResult(
            backend_type="kubernetes",
            url=backend.url,
            reachable=True,
            response_time_ms=round(response_time_ms, 1),
            details={
                "namespaces": ns_names,
                "namespace_count": len(ns_names),
                "chatcraft_namespace": "chatcraft" in ns_names,
            }
        )
    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        return BackendTestResult(
            backend_type="kubernetes",
            url=backend.url,
            reachable=False,
            response_time_ms=round(response_time_ms, 1),
            error=str(e)
        )


@router.post("/backends", response_model=BackendResponse, status_code=201)
async def create_backend(
    request: BackendCreateRequest,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """Create a backend configuration for a tenant (system admin only)."""
    # Check for existing backend of same type
    existing = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == request.tenant_id,
        ObservabilityBackend.backend_type == request.backend_type
    ).first()

    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Backend type '{request.backend_type}' already configured for this tenant"
        )

    # Encrypt credentials if provided
    encrypted_creds = None
    if request.credentials:
        encrypted_creds = credential_service.encrypt(request.credentials)

    backend = ObservabilityBackend(
        tenant_id=request.tenant_id,
        backend_type=request.backend_type,
        url=request.url,
        auth_type=request.auth_type,
        credentials_encrypted=encrypted_creds,
        verify_ssl=request.verify_ssl,
        timeout_seconds=request.timeout_seconds
    )

    db.add(backend)
    db.commit()
    db.refresh(backend)

    logger.info(f"Created {request.backend_type} backend for tenant {request.tenant_id}")
    return backend


@router.get("/backends", response_model=List[BackendResponse])
async def list_backends(
    tenant_id: str = None,
    claims: TokenClaims = Depends(validate_token_or_api_key),
    db: Session = Depends(get_db)
):
    """List backend configurations for a tenant."""
    target_tenant = tenant_id or claims.tenant_id

    if not claims.is_system_admin and target_tenant != claims.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot view backends for other tenants"
        )

    backends = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == target_tenant
    ).all()

    return backends


@router.put("/backends/{tenant_id}/{backend_type}", response_model=BackendResponse)
async def update_backend(
    tenant_id: str,
    backend_type: str,
    request: BackendUpdateRequest,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """Update a backend configuration (system admin only)."""
    backend = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == tenant_id,
        ObservabilityBackend.backend_type == backend_type
    ).first()

    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend '{backend_type}' not found for tenant"
        )

    if request.url is not None:
        backend.url = request.url
    if request.auth_type is not None:
        backend.auth_type = request.auth_type
    if request.credentials is not None:
        backend.credentials_encrypted = credential_service.encrypt(request.credentials)
    if request.verify_ssl is not None:
        backend.verify_ssl = request.verify_ssl
    if request.timeout_seconds is not None:
        backend.timeout_seconds = request.timeout_seconds
    if request.is_active is not None:
        backend.is_active = request.is_active

    db.commit()
    db.refresh(backend)
    return backend


@router.delete("/backends/{tenant_id}/{backend_type}", status_code=204)
async def delete_backend(
    tenant_id: str,
    backend_type: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """Delete a backend configuration (system admin only)."""
    backend = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == tenant_id,
        ObservabilityBackend.backend_type == backend_type
    ).first()

    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend '{backend_type}' not found for tenant"
        )

    db.delete(backend)
    db.commit()


@router.post("/backends/{tenant_id}/{backend_type}/test", response_model=BackendTestResult)
async def test_backend(
    tenant_id: str,
    backend_type: str,
    claims: TokenClaims = Depends(require_system_admin),
    db: Session = Depends(get_db)
):
    """Test connectivity to a backend (system admin only)."""
    backend = db.query(ObservabilityBackend).filter(
        ObservabilityBackend.tenant_id == tenant_id,
        ObservabilityBackend.backend_type == backend_type
    ).first()

    logger.info(f"Testing connectivity to {backend_type} backend for tenant {tenant_id}")
    logger.debug(backend)

    if not backend:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Backend '{backend_type}' not found for tenant"
        )

    # K8s backend — test via Kubernetes Python client, not HTTP
    if backend_type == "kubernetes":
        return _test_k8s_connectivity(backend)

    # Kafka backend — test via the Kafka Admin API, not HTTP
    if backend_type == "kafka":
        return _test_kafka_connectivity(backend)

    if not backend.url:
        return BackendTestResult(
            backend_type=backend_type,
            url=None,
            reachable=False,
            error="No URL configured"
        )

    # Test connectivity based on backend type
    test_paths = {
        "prometheus": "/api/v1/status/config",
        "alertmanager": "/api/v2/status",
        "elasticsearch": "/",
        "jaeger": "/api/services",
        "otel_collector": "/metrics",
        "llm": None,  # Skip HTTP test for LLM
    }

    test_path = test_paths.get(backend_type, "/health")

    if test_path is None:
        return BackendTestResult(
            backend_type=backend_type,
            url=backend.url,
            reachable=True,
            details={"note": "LLM backends are tested on first query"}
        )

    start_time = time.time()
    try:
        # Build auth headers
        headers = {"Content-Type": "application/json"}
        auth = None
        if backend.credentials_encrypted:
            creds = credential_service.decrypt(backend.credentials_encrypted)
            if creds and backend.auth_type == "bearer":
                headers["Authorization"] = f"Bearer {creds.get('token', '')}"
            elif creds and backend.auth_type == "basic":
                auth = (creds.get("username", ""), creds.get("password", ""))

        logger.info(f"Testing connectivity to {backend.url}{test_path}")
        async with httpx.AsyncClient(verify=backend.verify_ssl, timeout=backend.timeout_seconds) as client:
            response = await client.get(
                f"{backend.url}{test_path}",
                headers=headers,
                auth=auth
            )

        response_time_ms = (time.time() - start_time) * 1000

        return BackendTestResult(
            backend_type=backend_type,
            url=backend.url,
            reachable=response.status_code < 500,
            response_time_ms=round(response_time_ms, 1),
            details={"status_code": response.status_code}
        )

    except Exception as e:
        response_time_ms = (time.time() - start_time) * 1000
        return BackendTestResult(
            backend_type=backend_type,
            url=backend.url,
            reachable=False,
            response_time_ms=round(response_time_ms, 1),
            error=str(e)
        )

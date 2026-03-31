"""
Seed observability backend configurations for local testing.

Configures tenant 91ef69aa-ae68-48af-8397-b7f3c21f46a1 (Access Bank)
to connect to mock observability services running in local Kubernetes.

Usage:
    cd observability-service
    python seed_backends.py
"""
import os
import sys
from pathlib import Path

# Load .env before any app imports
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent / ".env", override=True)

from app.core.database import SessionLocal
from app.models.backend_config import ObservabilityBackend

TENANT_ID = "91ef69aa-ae68-48af-8397-b7f3c21f46a1"

BACKENDS = [
    {
        "backend_type": "prometheus",
        "url": "http://localhost:9090",
        "auth_type": "none",
        "verify_ssl": False,
        "timeout_seconds": 10.0,
    },
    {
        "backend_type": "alertmanager",
        "url": "http://localhost:9093",
        "auth_type": "none",
        "verify_ssl": False,
        "timeout_seconds": 10.0,
    },
    {
        "backend_type": "elasticsearch",
        "url": "http://localhost:9200",
        "auth_type": "none",
        "verify_ssl": False,
        "timeout_seconds": 10.0,
    },
    {
        "backend_type": "jaeger",
        "url": "http://localhost:16686",
        "auth_type": "none",
        "verify_ssl": False,
        "timeout_seconds": 10.0,
    },
    {
        "backend_type": "otel_collector",
        "url": "http://localhost:8888",
        "auth_type": "none",
        "verify_ssl": False,
        "timeout_seconds": 10.0,
    },
    {
        "backend_type": "kubernetes",
        "url": None,  # Uses local kubeconfig in dev, service_account token in prod
        "auth_type": "none",
        "verify_ssl": False,
        "timeout_seconds": 10.0,
    },
]


def seed():
    db = SessionLocal()
    try:
        for cfg in BACKENDS:
            existing = db.query(ObservabilityBackend).filter(
                ObservabilityBackend.tenant_id == TENANT_ID,
                ObservabilityBackend.backend_type == cfg["backend_type"],
            ).first()

            if existing:
                changed = []
                if existing.url != cfg["url"]:
                    changed.append(f"url: {existing.url} → {cfg['url']}")
                    existing.url = cfg["url"]
                if existing.verify_ssl != cfg["verify_ssl"]:
                    changed.append(f"verify_ssl: {existing.verify_ssl} → {cfg['verify_ssl']}")
                    existing.verify_ssl = cfg["verify_ssl"]
                if existing.timeout_seconds != cfg["timeout_seconds"]:
                    changed.append(f"timeout: {existing.timeout_seconds} → {cfg['timeout_seconds']}")
                    existing.timeout_seconds = cfg["timeout_seconds"]
                if existing.auth_type != cfg["auth_type"]:
                    changed.append(f"auth_type: {existing.auth_type} → {cfg['auth_type']}")
                    existing.auth_type = cfg["auth_type"]

                if changed:
                    print(f"  UPDATED  {cfg['backend_type']:20s} — {', '.join(changed)}")
                else:
                    print(f"  OK       {cfg['backend_type']:20s} — no changes needed")
            else:
                backend = ObservabilityBackend(
                    tenant_id=TENANT_ID,
                    backend_type=cfg["backend_type"],
                    url=cfg["url"],
                    auth_type=cfg["auth_type"],
                    verify_ssl=cfg["verify_ssl"],
                    timeout_seconds=cfg["timeout_seconds"],
                    is_active=True,
                )
                db.add(backend)
                url_display = cfg["url"] or "(kubeconfig)"
                print(f"  CREATED  {cfg['backend_type']:20s} → {url_display}")

        db.commit()
        print(f"\nDone. Tenant {TENANT_ID} now has {len(BACKENDS)} backends configured.")

    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    print(f"Seeding observability backends for tenant {TENANT_ID}\n")
    seed()

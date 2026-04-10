"""Plugin manifest endpoint.

Self-description returned by the observability service to the catalog
(billing-service) when it is registered. The catalog stores this verbatim and
replays the `ui_extensions` to the superadmin shell so the Observability and
LLM Providers menus can appear dynamically.

The manifest is intentionally unauthenticated — it contains no secrets, only
the public contract this service exposes.
"""
from fastapi import APIRouter

router = APIRouter()


# The api_prefix values below match the paths the gateway already exposes for
# observability admin (see gateway-service/src/main/resources/application.yml,
# routes `admin-observability` and `admin-llm-providers`). When those routes
# move to the @Profile-gated RouteLocator class, the prefixes stay the same.
_MANIFEST = {
    "service_key": "observability",
    "name": "DevOps Intelligence",
    "version": "1.0.0",
    "category": "agentic",
    "description": "AI-powered DevOps Intelligence agent for K8s, OpenTelemetry, "
                   "Prometheus, Elasticsearch, Jaeger  and Kafka backends.",
    "capabilities": {
        "query": True,
        "backends": ["kubernetes", "prometheus", "elasticsearch", "jaeger", "otel", "kafka"],
        "supports_streaming": False,
    },
    "triggers": ["observability", "metrics", "logs", "traces", "alerts"],
    "ui_extensions": [
        {
            "menu_label": "DevOps Intelligence",
            "icon": "monitoring",
            "route": "observability",
            "required_role": "SUPER_ADMIN",
            "api_prefix": "/api/v1/admin/observability",
        },
        {
            "menu_label": "LLM Providers",
            "icon": "smart_toy",
            "route": "llm-providers",
            "required_role": "SUPER_ADMIN",
            "api_prefix": "/api/v1/admin/llm-providers",
        },
    ],
    "settings_schema": None,
}


@router.get("/manifest")
async def get_manifest():
    return _MANIFEST
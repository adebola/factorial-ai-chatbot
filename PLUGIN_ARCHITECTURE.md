# Plugin / Agentic Service Architecture

ChatCraft supports **plugin services** (also called *agentic services*) — domain
services like `observability-service`, and future ones such as legal, medical,
loan-applications, etc. — that can be added or removed per environment without
changing the core. The first plugin is `observability-service`, originally
built for an on-prem client and **not deployed in default SaaS production**.

This document is the run-book for working with that architecture. Read it
before adding a new plugin or debugging why menus aren't appearing.

---

## Design principles

1. **Core depends on infrastructure; services depend on core. The core never
   imports or hard-codes a plugin.** The catalog stores opaque metadata; no
   typed knowledge of "observability" anywhere outside the plugin itself.
2. **Plugins are self-describing.** Each plugin exposes `GET /manifest` declaring
   its capabilities, UI extensions, and any settings schema.
3. **The catalog is the single source of truth for discovery + UI.**
   Registration writes the manifest into `billing-service.agentic_services`.
   The superadmin shell reads from the catalog, not from plugins directly.
4. **Fail-absent, not fail-error.** If a plugin is unregistered, unhealthy, or
   unreachable: hide its menu, return empty lists from discovery, and let
   chat-service's existing fail-open logic handle runtime calls.
5. **Gateway routes are per-plugin but conditionally registered via Spring
   profiles.** Routing config lives in code (`@Profile`-annotated
   `RouteLocator` beans), not YAML, so multiple plugins compose additively.
6. **Two loosely-coupled sources of truth:**
   - **Gateway `RouteLocator` beans** own *routing* (what is reachable, with
     what timeouts/filters).
   - **Billing-service catalog** owns *discovery + UI extensions* (what menus
     to render, which tenants are assigned).
   - The link between them is a string: `ui_extension.api_prefix` in the
     manifest must match a path the gateway exposes for that plugin. No code
     dependency.

---

## Components

### 1. The plugin manifest (`GET /manifest`)

Every plugin service exposes an unauthenticated `GET /manifest` endpoint
returning JSON that conforms to `PluginManifest`
(`billing-service/app/schemas/agentic_service.py`):

```json
{
  "service_key": "observability",
  "name": "Observability",
  "version": "1.0.0",
  "category": "agentic",
  "description": "AI-powered observability agent for K8s/OTel/Prometheus.",
  "capabilities": { "query": true, "backends": ["kubernetes", "prometheus"] },
  "triggers": ["observability", "metrics", "logs", "traces"],
  "ui_extensions": [
    {
      "menu_label": "Observability",
      "icon": "monitoring",
      "route": "observability",
      "required_role": "SUPER_ADMIN",
      "api_prefix": "/api/v1/admin/observability"
    },
    {
      "menu_label": "LLM Providers",
      "icon": "smart_toy",
      "route": "llm-providers",
      "required_role": "SUPER_ADMIN",
      "api_prefix": "/api/v1/admin/llm-providers"
    }
  ],
  "settings_schema": null
}
```

The manifest is **opaque to the core**. The catalog stores it as JSON and
replays the `ui_extensions` to the superadmin shell.

**Reference implementation:** `observability-service/app/api/manifest.py`,
mounted in `observability-service/app/main.py`.

### 2. The catalog (`billing-service`)

The catalog table `agentic_services` (managed by Alembic):

| Column                   | Purpose                                                |
| ------------------------ | ------------------------------------------------------ |
| `id`                     | UUID PK                                                |
| `name`, `service_key`    | Mirrored from manifest, `service_key` is the lookup    |
| `base_url`               | Where the plugin lives (catalog uses to refresh)       |
| `health_check_url`       | Optional explicit health endpoint                      |
| `category`               | "agentic" by default                                   |
| `capabilities`           | Mirrored from manifest                                 |
| `ui_hints`               | **In-chat widget** presentation (icon, branding) —     |
|                          | distinct from `ui_extensions` below                    |
| `manifest`               | Whole most-recent manifest, opaque JSON                |
| `ui_extensions`          | Denormalized list of admin-UI menu entries             |
| `health_status`          | `healthy` / `unhealthy` / `unknown`                    |
| `last_manifest_fetch_at` | Timestamp of last successful manifest pull             |
| `last_health_at`         | Timestamp of last health probe                         |
| `is_active`, `is_deleted`| Standard soft-state                                    |

**Catalog API** (`billing-service/app/api/agentic_services.py`, mounted at
`/api/v1/admin/services`):

| Endpoint                                          | Purpose                                                                 |
| ------------------------------------------------- | ----------------------------------------------------------------------- |
| `POST /services`                                   | Manual registration (legacy — prefer `register-by-url`)                |
| `POST /services/register-by-url`                   | Fetch `/manifest` from `base_url` and create or update catalog row     |
| `POST /services/{id}/refresh-manifest`             | Re-pull `/manifest` for an existing row                                |
| `GET /services`                                    | List all                                                                |
| `GET /services/{id}`                               | Detail                                                                  |
| `PUT /services/{id}`                               | Manual update                                                           |
| `DELETE /services/{id}`                            | Soft-delete                                                             |
| `GET /services/{id}/health`                        | Probe + persist `health_status`                                        |
| `GET /services/ui-extensions`                      | **Flat list of all UI extensions** — read by the superadmin shell      |
| `POST /services/{id}/assign`                       | Assign service to a tenant                                              |
| `DELETE /services/{id}/assign/{tenant_id}`         | Revoke from a tenant                                                    |

**Route ordering note:** literal-segment routes (`/services/ui-extensions`,
`/services/register-by-url`) MUST be declared *before* any
`/services/{service_id}` routes — FastAPI matches in declaration order. If you
add new literal endpoints, keep them above the parametrized block.

### 3. The gateway

All super-admin and tenant-admin traffic flows through the gateway, so each
plugin **must** have routes defined in the gateway. They are
**conditionally registered** via Spring profiles.

- **Plugin routes live in `gateway-service/src/main/java/io/factorialsystems/gatewayservice/plugins/`**, one
  `@Configuration @Profile("plugin-<key>")` class per plugin, exposing one
  `RouteLocator` bean. Spring Cloud Gateway concatenates *all* `RouteLocator`
  beans found in the context, so each active profile contributes additively.
- **Core routes** (auth, billing, chat, onboarding, audit, etc.) stay in
  `application.yml` — they are always active and not plugins.
- The detailed pattern is documented in
  `gateway-service/src/main/java/io/factorialsystems/gatewayservice/plugins/README.md`. **Read that file
  before adding a new plugin.**

**Why not YAML profile blocks?** Spring Boot does **not** merge list properties
across property sources — it replaces them. Two profile blocks each defining
`spring.cloud.gateway.routes` would clobber each other instead of stacking.
Programmatic `RouteLocator` beans are the only correct way to compose
profile-gated additive routes.

### 4. Chat-service runtime routing

`chat-service/app/services/agentic_client.py` discovers a tenant's active
agentic service via
`GET /api/v1/restrictions/check/active-agentic/{tenant_id}` (billing-service,
internal/no-auth, Redis-cached 5min) and routes user messages to the plugin
based on configured triggers. **It is already plugin-shaped and fail-open** —
if no service is registered for the tenant, it short-circuits and falls
through to the standard RAG/workflow path.

No changes are needed here when adding a new plugin, beyond registering the
plugin in the catalog and assigning it to tenants.

### 5. Superadmin shell

`chatcraft-superadmin` reads `GET /api/v1/admin/services/ui-extensions` on
bootstrap and renders the returned menu entries dynamically.

- **Service:** `src/app/core/services/plugin-catalog.service.ts` — caches in a
  `BehaviorSubject`, dedupes concurrent fetches, **fails open** (empty list)
  if the catalog is unreachable.
- **Layout:** `src/app/shared/layout/main-layout/main-layout.component.ts` —
  static `coreNavigationItems` (11 entries) + dynamic plugin entries appended
  from the catalog stream.
- **Guard:** `src/app/core/guards/plugin-availability.guard.ts` — applied to
  `/observability` and `/llm-providers` routes (and any future plugin routes).
  Redirects to `/dashboard` with a snackbar if the plugin is not in the
  catalog. Prevents bookmarked URLs from reaching feature modules whose
  backend isn't installed.
- **Route data contract:** `data: { pluginRoute: '<route>' }` on each
  plugin-gated route — the guard reads this to know which catalog entry to
  match against.

The Angular feature modules for `observability` and `llm-providers` remain in
the bundle even when the plugin is absent — they are dead code in that case
but cause no errors because the menu doesn't surface and the guard blocks
navigation.

---

## Adding a new plugin (worked example: `legal-service`)

1. **Implement the plugin service.** Validate JWTs against the auth server
   (use the shared auth helper if available). Expose your domain endpoints
   plus an unauthenticated `GET /manifest` returning a `PluginManifest`.

   ```python
   # legal-service/app/api/manifest.py
   from fastapi import APIRouter
   router = APIRouter()

   _MANIFEST = {
       "service_key": "legal",
       "name": "Legal",
       "version": "1.0.0",
       "category": "agentic",
       "description": "Legal document review and contract analysis.",
       "capabilities": {"contract_review": True, "case_search": True},
       "triggers": ["contract", "legal", "lawsuit", "case"],
       "ui_extensions": [
           {
               "menu_label": "Legal Cases",
               "icon": "gavel",
               "route": "legal",
               "required_role": "SUPER_ADMIN",
               "api_prefix": "/api/v1/admin/legal",
           },
       ],
       "settings_schema": None,
   }

   @router.get("/manifest")
   async def get_manifest():
       return _MANIFEST
   ```

2. **Add gateway routes** in
   `gateway-service/src/main/java/io/factorialsystems/gatewayservice/plugins/LegalPluginRoutes.java`:

   ```java
   @Slf4j
   @Configuration
   @Profile("plugin-legal")
   public class LegalPluginRoutes {

       @Value("${legal.service.url:http://localhost:8010}")
       private String legalUri;

       @Bean
       public RouteLocator legalRouteLocator(RouteLocatorBuilder builder) {
           log.info("Loading the Legal PlugIn with Url {}", legalUri);
           return builder.routes()
               .route("legal-api", r -> r
                   .path("/api/v1/legal/**")
                   .uri(legalUri))
               .route("admin-legal", r -> r
                   .path("/api/v1/admin/legal/**")
                   .filters(f -> f.rewritePath(
                       "/api/v1/admin/legal/(?<segment>.*)",
                       "/api/v1/legal/admin/${segment}"))
                   .uri(legalUri))
               .build();
       }
   }
   ```

   The `api_prefix` in your manifest (`/api/v1/admin/legal`) must match a
   path that this `RouteLocator` exposes.

3. **Activate the profile** in the environments where the plugin is deployed:

   ```bash
   SPRING_PROFILES_ACTIVE=production,plugin-observability,plugin-legal
   ```

   Or define a profile group in `gateway-service/src/main/resources/application.yml`:

   ```yaml
   spring:
     profiles:
       group:
         on-prem-clientB: production,plugin-observability,plugin-legal
   ```

   then `SPRING_PROFILES_ACTIVE=on-prem-clientB`.

4. **Register the plugin in the catalog** via the superadmin (or a one-shot
   curl from the deployment script):

   ```bash
   curl -X POST http://gateway/api/v1/admin/services/register-by-url \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"base_url": "http://legal-service:8010"}'
   ```

   The catalog calls `GET {base_url}/manifest`, validates it, and creates or
   updates the row. Idempotent — re-running it just refreshes the manifest.

5. **Assign the plugin to tenants** (existing endpoint):

   ```bash
   curl -X POST http://gateway/api/v1/admin/services/{service_id}/assign \
        -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"tenant_id": "...", "config": {...}}'
   ```

6. **Refresh the superadmin** browser. The new menu entry appears in the
   sidenav. Chat-service's `agentic_client` will discover the plugin for
   assigned tenants automatically (5-minute Redis cache).

That's it. Zero edits to existing core or other-plugin code.

---

## Per-environment matrix

| Environment      | `SPRING_PROFILES_ACTIVE`                                | Active gateway plugin routes        | Catalog entries                 |
| ---------------- | ------------------------------------------------------- | ----------------------------------- | ------------------------------- |
| SaaS production  | `production`                                            | (none)                              | (none — `register-by-url` not run) |
| On-prem client A | `production,plugin-observability`                       | observability                       | observability                   |
| On-prem client B | `production,plugin-observability,plugin-legal`          | observability + legal               | observability + legal           |
| Dev all-in       | `dev,plugin-observability,plugin-legal,plugin-medical`  | all three                           | all three (after registration)  |

---

## Verification / smoke test

End-to-end after a fresh deploy or after registering a new plugin:

1. **Manifest reachable from inside the deployment**
   ```bash
   curl http://<plugin-service>:<port>/manifest
   ```
   Should return valid JSON parseable by `PluginManifest`.

2. **Catalog registered**
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
        http://gateway/api/v1/admin/services/register-by-url \
        -d '{"base_url": "http://<plugin-service>:<port>"}'
   ```
   Should return 201/200 with the catalog row populated.

3. **UI extensions endpoint**
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
        http://gateway/api/v1/admin/services/ui-extensions
   ```
   Should include one entry per `ui_extensions` item from the manifest.

4. **Health probe**
   ```bash
   curl -H "Authorization: Bearer $TOKEN" \
        http://gateway/api/v1/admin/services/{id}/health
   ```
   Should return `{"status": "healthy"}` and persist `health_status` on the
   row (verify with `SELECT health_status, last_health_at FROM agentic_services`).

5. **Gateway route exposed**
   ```bash
   curl -i -H "Authorization: Bearer $TOKEN" \
        http://gateway/api/v1/admin/<plugin>/...
   ```
   Should reach the plugin (200 / 4xx based on the request — but **never** 404
   from the gateway).

6. **Superadmin menu rendering** — refresh the browser, confirm the new menu
   entry appears in the sidenav. Click it and verify the lazy-loaded module
   loads and makes successful API calls through the gateway.

7. **Plugin-absent simulation** — stop the plugin container, then either:
   - Soft-delete the catalog row (`DELETE /api/v1/admin/services/{id}`); or
   - Restart the gateway without the plugin profile.

   After a superadmin browser refresh:
   - The menu entry disappears.
   - Bookmarked navigation to `/observability` (or wherever) hits
     `PluginAvailabilityGuard`, shows a snackbar, and redirects to
     `/dashboard`.
   - Browser network tab shows **zero failed requests**.

---

## Troubleshooting

| Symptom                                                              | Likely cause                                                                                              | Where to look                                                                       |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Plugin menu doesn't appear in superadmin                             | Catalog row missing, `is_active=false`, or `ui_extensions` is null/empty                                  | `SELECT id, name, is_active, ui_extensions FROM agentic_services WHERE service_key='...'` |
| Menu appears but clicking it 404s at the gateway                     | Profile not active OR route path mismatch between manifest's `api_prefix` and the `RouteLocator` bean     | Gateway logs at startup, `RouteLocator` Java file, manifest JSON                    |
| Menu appears but clicking it 502/connection refused                  | Plugin container not running OR gateway pointing at wrong URL                                             | `observability.service.url` (or equivalent) override, plugin container logs         |
| Catalog shows `health_status=unhealthy`                              | Last health probe failed                                                                                  | `GET /api/v1/admin/services/{id}/health` to re-probe and see the error              |
| `register-by-url` returns 502                                        | Plugin's `/manifest` is unreachable from billing-service or returns invalid JSON                          | Test `curl <base_url>/manifest` from inside the billing-service network             |
| Chat-service doesn't trigger the plugin                              | Tenant not assigned, OR Redis cache stale (5min TTL), OR triggers don't match the user message           | `redis-cli DEL active_agentic:<tenant_id>` to bust cache; check `triggers` in manifest |
| Editing an agentic service in superadmin returns 422                 | Form sent empty string `""` for `capabilities` / `ui_hints`                                               | Already fixed: `service-form-dialog.component.ts::parseJsonField` + backend `_empty_str_to_none` validator |
| Two `RouteLocator` beans collide                                     | Same route ID (e.g. two plugins both naming a route `admin-something`)                                    | Spring Cloud Gateway logs at startup will warn — rename one                         |
| Adding a new gateway route does nothing                              | Profile typo OR class missed by component scan (must be under the `io.factorialsystems.gatewayservice` package tree) | Gateway logs — search for the `RouteLocator` bean name                              |

---

## Out of scope (deliberate, future work)

- **Module Federation** — letting plugins ship their own Angular code instead
  of bundling all feature modules into the superadmin app.
- **Generic plugin shell** — a single Angular component that renders simple
  CRUD forms from a manifest's `settings_schema`, suitable for lightweight
  plugins that don't justify a custom feature module.
- **Plugin marketplace UI / one-click install.**
- **Per-plugin secrets vault and sandboxing.**
- **Plugin-level rate limiting at the gateway.**
- **Migrating the billing-service `LLMProviderConfig` cost-tracking registry
  into a plugin** — different concern, not user-facing in the same way.

---

## File index

| Concern                        | Files                                                                                              |
| ------------------------------ | -------------------------------------------------------------------------------------------------- |
| Plugin manifest contract       | `billing-service/app/schemas/agentic_service.py` (`PluginManifest`, `PluginUiExtension`)           |
| Reference plugin manifest      | `observability-service/app/api/manifest.py`                                                        |
| Catalog model                  | `billing-service/app/models/agentic_service.py`                                                    |
| Catalog endpoints              | `billing-service/app/api/agentic_services.py`                                                      |
| Catalog migration              | `billing-service/alembic/versions/20260408_add_plugin_manifest_fields.py`                          |
| Gateway plugin routes          | `gateway-service/src/main/java/io/factorialsystems/gatewayservice/plugins/`                        |
| Gateway plugin pattern docs    | `gateway-service/src/main/java/io/factorialsystems/gatewayservice/plugins/README.md`               |
| Chat-service plugin client     | `chat-service/app/services/agentic_client.py`                                                      |
| Superadmin catalog client      | `chatcraft-superadmin/src/app/core/services/plugin-catalog.service.ts`                             |
| Superadmin layout (dynamic)    | `chatcraft-superadmin/src/app/shared/layout/main-layout/main-layout.component.ts`                  |
| Superadmin route guard         | `chatcraft-superadmin/src/app/core/guards/plugin-availability.guard.ts`                            |
| Superadmin routing             | `chatcraft-superadmin/src/app/app-routing.module.ts`                                               |
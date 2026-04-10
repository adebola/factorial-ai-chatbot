# Plugin (Agentic Service) Gateway Routes

This package holds gateway routes that belong to **agentic plugin services** —
services that may or may not be deployed in a given environment, such as
`observability-service`, `legal-service`, `medical-service`, etc.

## Why this exists

Core gateway routes (auth, billing, chat, onboarding, audit, …) live in
`application.yml` because they are always present. Plugin routes need to be
**conditionally registered**: a plugin that is not deployed in this environment
must contribute zero routes, with no errors and no special handling.

## Why not YAML profile blocks

Spring Boot does **not** merge list properties across profile-specific
property sources. Two profiles each declaring `spring.cloud.gateway.routes`
clobber each other instead of stacking. This is a hard limitation of Spring
Boot's relaxed list binding — a plugin-routes-via-YAML approach simply cannot
compose multiple plugins.

## The pattern

Each plugin gets one `@Configuration @Profile("plugin-<key>")` class in this
package, exposing a `RouteLocator` bean. Spring Cloud Gateway picks up
**every** `RouteLocator` bean it finds in the context and concatenates them,
so each active profile contributes additively.

Example skeleton:

```java
@Configuration
@Profile("plugin-legal")
public class LegalPluginRoutes {

    @Value("${legal.service.url:http://localhost:8010}")
    private String legalUri;

    @Bean
    public RouteLocator legalRouteLocator(RouteLocatorBuilder builder) {
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

## Activating plugins per environment

Plugin profiles are activated via `SPRING_PROFILES_ACTIVE` (env var) or
`-Dspring.profiles.active`. Stack them comma-separated:

| Environment      | `SPRING_PROFILES_ACTIVE`                              |
|------------------|-------------------------------------------------------|
| SaaS production  | `production`                                          |
| On-prem client A | `production,plugin-observability`                     |
| On-prem client B | `production,plugin-observability,plugin-legal`        |
| Dev all-in       | `dev,plugin-observability,plugin-legal,plugin-medical`|

Optionally collapse stacks behind a profile group in `application.yml`:

```yaml
spring:
  profiles:
    group:
      on-prem-clientA: production,plugin-observability
```

Then use `SPRING_PROFILES_ACTIVE=on-prem-clientA`.

## Path convention

For new plugins, prefer the path convention `/api/v1/plugins/{service_key}/**`
so the catalog's manifest `api_prefix` field is mechanically derivable. The
existing observability routes (`/api/v1/observe/**`,
`/api/v1/admin/observability/**`, `/api/v1/admin/llm-providers/**`) are kept
as-is to avoid churn — both conventions coexist because the
billing-service catalog stores `api_prefix` as an opaque string.

## Coordinating with the billing-service catalog

There are two loosely-coupled sources of truth:

- **Gateway `RouteLocator` beans (this package)** own *routing* — what is
  reachable, with what timeouts/filters.
- **Billing-service `agentic_services` catalog** owns *discovery + UI
  extensions* — what menus to render in the superadmin shell, which tenants
  are assigned, the manifest metadata.

The link between them is a string: each `ui_extensions[*].api_prefix` returned
by a plugin's `GET /manifest` must match a path that the gateway exposes for
that plugin. There is no code dependency.

## Adding a new plugin

1. Implement the plugin service. Expose `GET /manifest` (see
   `billing-service/app/schemas/agentic_service.py::PluginManifest`).
2. Add a new class here: `XxxPluginRoutes.java`, `@Profile("plugin-xxx")`,
   one `RouteLocator` bean.
3. Deploy the plugin container alongside this gateway in environments where
   the plugin is needed.
4. Add `plugin-xxx` to `SPRING_PROFILES_ACTIVE` (or to a profile group).
5. Operator calls
   `POST /api/v1/admin/services/register-by-url` against billing-service to
   register the plugin in the catalog. Menu entries appear in the superadmin
   shell on next bootstrap.
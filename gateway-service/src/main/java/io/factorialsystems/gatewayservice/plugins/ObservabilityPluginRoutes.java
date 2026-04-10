package io.factorialsystems.gatewayservice.plugins;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.gateway.route.RouteLocator;
import org.springframework.cloud.gateway.route.builder.RouteLocatorBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

/**
 * Gateway routes contributed by the observability agentic plugin.
 *
 * <p>This entire {@code @Configuration} is gated by the {@code plugin-observability}
 * Spring profile. When the profile is not active (e.g. in default SaaS production)
 * the bean is not registered, the routes do not exist, and any request to
 * {@code /api/v1/observe/**} or the admin paths returns the gateway's standard 404.
 *
 * <p>Spring Cloud Gateway concatenates <em>all</em> {@code RouteLocator} beans found
 * in the application context, so each plugin profile contributes additively. This
 * is the correct way to compose profile-gated gateway routes — YAML profile blocks
 * cannot do this because Spring Boot replaces (rather than merges) list properties
 * across property sources.
 *
 * <p>To activate locally / on-prem:
 * <pre>SPRING_PROFILES_ACTIVE=production,plugin-observability</pre>
 *
 * <p>The original YAML stanzas this class replaces lived in
 * {@code application.yml} as routes {@code observability-api},
 * {@code admin-observability-root}, {@code admin-observability},
 * {@code admin-llm-providers-root}, and {@code admin-llm-providers}.
 *
 * @see io.factorialsystems.gatewayservice.plugins.README.md
 */

@Configuration
@Profile("plugin-observability")
public class ObservabilityPluginRoutes {

    // Explicit SLF4J init — Lombok's @Slf4j is technically a dep but the
    // maven-compiler-plugin in this project isn't configured with the Lombok
    // annotation processor, so `mvn compile` cannot resolve a Lombok-injected
    // `log` field. IDE Lombok plugins mask this, so it looks fine in IntelliJ.
    private static final Logger log = LoggerFactory.getLogger(ObservabilityPluginRoutes.class);

    /**
     * Base URL of the observability service. Defaults to the dev port and is
     * overridable per environment via {@code OBSERVABILITY_SERVICE_URL} or the
     * {@code observability.service.url} property.
     */
    @Value("${observability.service.url:http://localhost:8006}")
    private String observabilityUri;

    @Bean
    public RouteLocator observabilityRouteLocator(RouteLocatorBuilder builder) {
        log.info("Loading the Observability PlugIn with Url {}", observabilityUri);

        return builder.routes()
                // ── Direct passthrough: /api/v1/observe/** ──
                // Long timeout because the agentic LLM query can take >30s.
                .route("observability-api", r -> r
                        .path("/api/v1/observe/**")
                        .filters(f -> f
                                .rewriteLocationResponseHeader("AS_IN_REQUEST", "Location", null, null))
                        .metadata("response-timeout", 120_000)
                        .metadata("connect-timeout", 5_000)
                        .uri(observabilityUri))

                // ── Admin: backends CRUD ──
                // /api/v1/admin/observability         -> /api/v1/observe/backends
                // /api/v1/admin/observability/{seg..} -> /api/v1/observe/backends/{seg..}
                .route("admin-observability-root", r -> r
                        .path("/api/v1/admin/observability")
                        .filters(f -> f
                                .rewritePath(
                                        "/api/v1/admin/observability",
                                        "/api/v1/observe/backends")
                                .rewriteLocationResponseHeader("AS_IN_REQUEST", "Location", null, null))
                        .uri(observabilityUri))

                .route("admin-observability", r -> r
                        .path("/api/v1/admin/observability/**")
                        .filters(f -> f
                                .rewritePath(
                                        "/api/v1/admin/observability/(?<segment>.*)",
                                        "/api/v1/observe/backends/${segment}")
                                .rewriteLocationResponseHeader("AS_IN_REQUEST", "Location", null, null))
                        .uri(observabilityUri))

                // ── Admin: LLM provider catalog ──
                // /api/v1/admin/llm-providers         -> /api/v1/observe/llm-providers
                // /api/v1/admin/llm-providers/{seg..} -> /api/v1/observe/llm-providers/{seg..}
                .route("admin-llm-providers-root", r -> r
                        .path("/api/v1/admin/llm-providers")
                        .filters(f -> f
                                .rewritePath(
                                        "/api/v1/admin/llm-providers",
                                        "/api/v1/observe/llm-providers")
                                .rewriteLocationResponseHeader("AS_IN_REQUEST", "Location", null, null))
                        .uri(observabilityUri))

                .route("admin-llm-providers", r -> r
                        .path("/api/v1/admin/llm-providers/**")
                        .filters(f -> f
                                .rewritePath(
                                        "/api/v1/admin/llm-providers/(?<segment>.*)",
                                        "/api/v1/observe/llm-providers/${segment}")
                                .rewriteLocationResponseHeader("AS_IN_REQUEST", "Location", null, null))
                        .uri(observabilityUri))

                // ── Health probe ──
                // /health/observability -> {observabilityUri}/health
                .route("observability-health", r -> r
                        .path("/health/observability")
                        .filters(f -> f.rewritePath("/health/observability", "/health"))
                        .uri(observabilityUri))
                .build();
    }
}
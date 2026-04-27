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
 * Gateway routes contributed by the legal agentic plugin.
 *
 * <p>Gated by the {@code plugin-legal} Spring profile. When inactive, no
 * legal-service routes exist and any request to {@code /api/v1/legal/**}
 * returns the gateway's standard 404.
 *
 * <p>Activate with: {@code SPRING_PROFILES_ACTIVE=...,plugin-legal}
 *
 * @see io.factorialsystems.gatewayservice.plugins.README.md
 */
@Configuration
@Profile("plugin-legal")
public class LegalPluginRoutes {

    private static final Logger log = LoggerFactory.getLogger(LegalPluginRoutes.class);

    @Value("${legal.service.url:http://localhost:8010}")
    private String legalUri;

    @Bean
    public RouteLocator legalRouteLocator(RouteLocatorBuilder builder) {
        log.info("Loading the Legal PlugIn with Url {}", legalUri);

        return builder.routes()
                // Direct passthrough: /api/v1/legal/**
                // Extended timeout for LLM agent queries which can take >30s.
                .route("legal-api", r -> r
                        .path("/api/v1/legal/**")
                        .filters(f -> f
                                .rewriteLocationResponseHeader("AS_IN_REQUEST", "Location", null, null))
                        .metadata("response-timeout", 120_000)
                        .metadata("connect-timeout", 5_000)
                        .uri(legalUri))

                // Admin routes (for future superadmin screens)
                .route("admin-legal", r -> r
                        .path("/api/v1/admin/legal/**")
                        .filters(f -> f
                                .rewritePath(
                                        "/api/v1/admin/legal/(?<segment>.*)",
                                        "/api/v1/legal/admin/${segment}")
                                .rewriteLocationResponseHeader("AS_IN_REQUEST", "Location", null, null))
                        .uri(legalUri))

                // Health probe
                .route("legal-health", r -> r
                        .path("/health/legal")
                        .filters(f -> f.rewritePath("/health/legal", "/health"))
                        .uri(legalUri))
                .build();
    }
}

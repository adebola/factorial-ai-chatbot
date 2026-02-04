package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

@Slf4j
@Service
@RequiredArgsConstructor
public class BillingServiceClient {

    private final ObjectMapper objectMapper;
    private final StringRedisTemplate redisTemplate;

    @Value("${billing.service.url:http://localhost:8004}")
    private String billingServiceUrl;

    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    /**
     * Get the free-tier plan from the billing service.
     * First checks Redis cache (managed by billing service), then falls back to API call.
     *
     * IMPORTANT: This service only READS from cache. The billing service is responsible
     * for managing the cache lifecycle (write/invalidate).
     *
     * @return Free-tier plan information as JsonNode
     * @throws RuntimeException if the plan cannot be retrieved
     */
    public JsonNode getFreeTierPlan() {
        // Use the same cache key format as billing service
        String cacheKey = "plan:free_tier";

        try {
            // Try to get from Redis cache first (read-only)
            String cachedPlan = redisTemplate.opsForValue().get(cacheKey);
            if (cachedPlan != null && !cachedPlan.isEmpty()) {
                log.debug("Retrieved free-tier plan from shared Redis cache (managed by billing service)");
                return objectMapper.readTree(cachedPlan);
            }

            // Not in cache, call the billing service
            log.info("Free-tier plan not in shared cache, calling billing service");
            JsonNode planData = fetchFreeTierPlanFromService();

            // DO NOT cache here - let the billing service handle all cache management
            log.info("Retrieved free-tier plan from billing service API (cache will be managed by billing service)");

            return planData;

        } catch (Exception e) {
            log.error("Failed to retrieve free-tier plan from billing service: {}", e.getMessage(), e);
            throw new RuntimeException("Unable to retrieve free-tier plan from billing service: " + e.getMessage(), e);
        }
    }

    /**
     * Extract the plan ID from the free-tier plan data
     *
     * @return Plan ID string
     * @throws RuntimeException if plan ID cannot be extracted
     */
    public String getFreeTierPlanId() {
        JsonNode planData = getFreeTierPlan();
        JsonNode planIdNode = planData.get("id");

        if (planIdNode == null || planIdNode.isNull()) {
            log.error("No plan ID found in free-tier plan data from billing service");
            throw new RuntimeException("Free-tier plan ID not found in billing service response");
        }

        String planId = planIdNode.asText();
        log.debug("Retrieved free-tier plan ID from billing service: {}", planId);
        return planId;
    }

    /**
     * Call the billing service API to get the free-tier plan.
     *
     * IMPORTANT: This calls the billing service's /api/v1/plans/free-tier endpoint
     * which handles its own caching. The billing service will check its cache first,
     * then populate the cache if needed.
     *
     * @return Free-tier plan as JsonNode
     * @throws Exception if the API call fails
     */
    private JsonNode fetchFreeTierPlanFromService() throws Exception {
        // Use the dedicated free-tier endpoint that handles caching
        String url = billingServiceUrl + "/api/v1/plans/free-tier";

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(30))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .GET()
                .build();

        log.debug("Calling billing service free-tier endpoint at: {}", url);

        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            log.error("Billing service returned status {}: {}", response.statusCode(), response.body());
            throw new RuntimeException(
                String.format("Billing service error: HTTP %d - %s",
                    response.statusCode(), response.body())
            );
        }

        String responseBody = response.body();
        JsonNode responseJson = objectMapper.readTree(responseBody);

        // The free-tier endpoint returns the plan directly, not in an array
        JsonNode planIdNode = responseJson.get("id");
        if (planIdNode == null || planIdNode.isNull()) {
            log.error("Invalid response format: no plan ID found in billing service free-tier response");
            throw new RuntimeException("Invalid response format from billing service free-tier endpoint");
        }

        log.debug("Successfully retrieved free-tier plan from billing service");
        return responseJson;
    }

    /**
     * Check if the billing service is available
     *
     * @return true if the service is reachable, false otherwise
     */
    public boolean isBillingServiceAvailable() {
        try {
            String url = billingServiceUrl + "/health";

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            return response.statusCode() == 200;

        } catch (Exception e) {
            log.warn("Billing service health check failed: {}", e.getMessage());
            return false;
        }
    }

    /**
     * Get subscription details by tenant ID
     *
     * @param tenantId The tenant ID
     * @param authorizationHeader The Authorization header from the incoming request (e.g., "Bearer token...")
     * @return Subscription data as a Map
     * @throws Exception if the API call fails
     */
    public java.util.Map<String, Object> getSubscriptionByTenant(String tenantId, String authorizationHeader) throws Exception {
        String url = billingServiceUrl + "/api/v1/billing/admin/subscriptions/tenant/" + tenantId;

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header("Authorization", authorizationHeader)
                .GET()
                .build();

        log.debug("Fetching subscription from billing service for tenant: {}", tenantId);

        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            log.error("Billing service returned status {}: {}", response.statusCode(), response.body());
            throw new RuntimeException(
                String.format("Failed to fetch subscription: HTTP %d - %s",
                    response.statusCode(), response.body())
            );
        }

        return objectMapper.readValue(response.body(), java.util.Map.class);
    }

    /**
     * Get platform-wide metrics from billing service
     *
     * @param authorizationHeader The Authorization header from the incoming request (e.g., "Bearer token...")
     * @return Platform metrics as a Map
     * @throws Exception if the API call fails
     */
    public java.util.Map<String, Object> getPlatformMetrics(String authorizationHeader) throws Exception {
        String url = billingServiceUrl + "/api/v1/analytics/dashboard";

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header("Authorization", authorizationHeader)
                .GET()
                .build();

        log.debug("Fetching platform metrics from billing service");

        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            log.error("Billing service returned status {}: {}", response.statusCode(), response.body());
            throw new RuntimeException(
                String.format("Failed to fetch platform metrics: HTTP %d - %s",
                    response.statusCode(), response.body())
            );
        }

        return objectMapper.readValue(response.body(), java.util.Map.class);
    }

    /**
     * Get revenue analytics from billing service
     *
     * @param authorizationHeader The Authorization header from the incoming request (e.g., "Bearer token...")
     * @return Revenue analytics as a Map
     * @throws Exception if the API call fails
     */
    public java.util.Map<String, Object> getRevenueAnalytics(String authorizationHeader) throws Exception {
        String url = billingServiceUrl + "/api/v1/analytics/revenue";

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header("Authorization", authorizationHeader)
                .GET()
                .build();

        log.debug("Fetching revenue analytics from billing service");

        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            log.error("Billing service returned status {}: {}", response.statusCode(), response.body());
            throw new RuntimeException(
                String.format("Failed to fetch revenue analytics: HTTP %d - %s",
                    response.statusCode(), response.body())
            );
        }

        return objectMapper.readValue(response.body(), java.util.Map.class);
    }
}

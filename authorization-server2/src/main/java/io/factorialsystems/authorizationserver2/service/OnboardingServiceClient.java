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
import java.util.concurrent.TimeUnit;

@Slf4j
@Service
@RequiredArgsConstructor
public class OnboardingServiceClient {

    private final ObjectMapper objectMapper;
    private final StringRedisTemplate redisTemplate;
    
    @Value("${onboarding.service.url:http://localhost:8001}")
    private String onboardingServiceUrl;
    
    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    /**
     * Get the free-tier plan from the onboarding service.
     * First checks Redis cache (managed by onboarding service), then falls back to API call.
     *
     * IMPORTANT: This service only READS from cache. The onboarding service is responsible
     * for managing the cache lifecycle (write/invalidate).
     *
     * @return Free-tier plan information as JsonNode
     * @throws RuntimeException if the plan cannot be retrieved
     */
    public JsonNode getFreeTierPlan() {
        // Use the same cache key format as onboarding service
        String cacheKey = "plan:free_tier";

        try {
            // Try to get from Redis cache first (read-only)
            String cachedPlan = redisTemplate.opsForValue().get(cacheKey);
            if (cachedPlan != null && !cachedPlan.isEmpty()) {
                log.debug("Retrieved free-tier plan from shared Redis cache (managed by onboarding service)");
                return objectMapper.readTree(cachedPlan);
            }

            // Not in cache, call the onboarding service
            log.info("Free-tier plan not in shared cache, calling onboarding service");
            JsonNode planData = fetchFreeTierPlanFromService();

            // DO NOT cache here - let the onboarding service handle all cache management
            log.debug("Retrieved free-tier plan from onboarding service API (cache will be managed by onboarding service)");

            return planData;

        } catch (Exception e) {
            log.error("Failed to retrieve free-tier plan: {}", e.getMessage(), e);
            throw new RuntimeException("Unable to retrieve free-tier plan: " + e.getMessage(), e);
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
            log.error("No plan ID found in free-tier plan data");
            throw new RuntimeException("Free-tier plan ID not found");
        }
        
        String planId = planIdNode.asText();
        log.debug("Retrieved free-tier plan ID: {}", planId);
        return planId;
    }
    
    /**
     * Call the onboarding service API to get the free-tier plan.
     *
     * IMPORTANT: This calls the onboarding service's /api/v1/plans/free-tier endpoint
     * which handles its own caching. The onboarding service will check its cache first,
     * then populate the cache if needed.
     *
     * @return Free-tier plan as JsonNode
     * @throws Exception if the API call fails
     */
    private JsonNode fetchFreeTierPlanFromService() throws Exception {
        // Use the dedicated free-tier endpoint that handles caching
        String url = onboardingServiceUrl + "/api/v1/plans/free-tier";
        
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(30))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .GET()
                .build();
        
        log.debug("Calling onboarding service free-tier endpoint at: {}", url);

        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            log.error("Onboarding service returned status {}: {}", response.statusCode(), response.body());
            throw new RuntimeException(
                String.format("Onboarding service error: HTTP %d - %s",
                    response.statusCode(), response.body())
            );
        }

        String responseBody = response.body();
        JsonNode responseJson = objectMapper.readTree(responseBody);

        // The free-tier endpoint returns the plan directly, not in an array
        JsonNode planIdNode = responseJson.get("id");
        if (planIdNode == null || planIdNode.isNull()) {
            log.error("Invalid response format: no plan ID found in free-tier response");
            throw new RuntimeException("Invalid response format from onboarding service free-tier endpoint");
        }

        log.debug("Successfully retrieved free-tier plan from onboarding service");
        return responseJson;
    }
    
    /**
     * Check if the onboarding service is available
     *
     * @return true if the service is reachable, false otherwise
     */
    public boolean isOnboardingServiceAvailable() {
        try {
            String url = onboardingServiceUrl + "/health";
            
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();
            
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            return response.statusCode() == 200;
            
        } catch (Exception e) {
            log.warn("Onboarding service health check failed: {}", e.getMessage());
            return false;
        }
    }
}
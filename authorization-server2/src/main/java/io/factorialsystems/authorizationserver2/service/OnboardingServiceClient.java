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
     * First checks Redis cache, then falls back to API call.
     *
     * @return Free-tier plan information as JsonNode
     * @throws RuntimeException if the plan cannot be retrieved
     */
    public JsonNode getFreeTierPlan() {
        String cacheKey = "free_tier_plan";
        
        try {
            // Try to get from Redis cache first
            String cachedPlan = redisTemplate.opsForValue().get(cacheKey);
            if (cachedPlan != null && !cachedPlan.isEmpty()) {
                log.debug("Retrieved free-tier plan from Redis cache");
                return objectMapper.readTree(cachedPlan);
            }
            
            // Not in cache, call the onboarding service
            log.info("Free-tier plan not in cache, calling onboarding service");
            JsonNode planData = fetchFreeTierPlanFromService();
            
            // Cache the result for future use (let the onboarding service handle its own caching)
            // We just cache locally for a short time to avoid repeated calls
            redisTemplate.opsForValue().set(cacheKey, planData.toString(), Duration.ofMinutes(5));
            log.debug("Cached free-tier plan locally for 5 minutes");
            
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
     * Call the onboarding service API to get the free-tier plan
     * Uses the public plans endpoint and filters for the Free plan
     *
     * @return Free-tier plan as JsonNode
     * @throws Exception if the API call fails
     */
    private JsonNode fetchFreeTierPlanFromService() throws Exception {
        String url = onboardingServiceUrl + "/api/v1/plans/public";
        
        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(30))
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .GET()
                .build();
        
        log.debug("Calling onboarding service public plans endpoint at: {}", url);
        
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
        
        // Extract plans array
        JsonNode plansArray = responseJson.get("plans");
        if (plansArray == null || !plansArray.isArray()) {
            log.error("Invalid response format: no plans array found");
            throw new RuntimeException("Invalid response format from onboarding service");
        }
        
        // Find the Free plan
        for (JsonNode plan : plansArray) {
            JsonNode nameNode = plan.get("name");
            if (nameNode != null && "Free".equals(nameNode.asText())) {
                log.debug("Found Free plan in response");
                return plan;
            }
        }
        
        log.error("Free plan not found in the plans list");
        throw new RuntimeException("Free plan not found in onboarding service response");
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
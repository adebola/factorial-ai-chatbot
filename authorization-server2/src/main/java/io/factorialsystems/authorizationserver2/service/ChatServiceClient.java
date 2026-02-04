package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

/**
 * HTTP client for communicating with the Chat Service.
 * Handles chat statistics retrieval and service health checks.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ChatServiceClient {

    private final ObjectMapper objectMapper;

    @Value("${chat.service.url:http://localhost:8000}")
    private String chatServiceUrl;

    private final HttpClient httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    /**
     * Get chat statistics for a specific tenant or system-wide
     *
     * @param tenantId The tenant ID to filter by (null for system-wide stats)
     * @param authorizationHeader The Authorization header from the incoming request (e.g., "Bearer token...")
     * @return Chat statistics as a Map
     * @throws Exception if the API call fails
     */
    public java.util.Map<String, Object> getChatStats(String tenantId, String authorizationHeader) throws Exception {
        String url = chatServiceUrl + "/api/v1/chat/admin/stats";

        // Add tenant_id query parameter if provided
        if (tenantId != null && !tenantId.isEmpty()) {
            url += "?tenant_id=" + tenantId;
        }

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .timeout(Duration.ofSeconds(10))
                .header("Content-Type", "application/json")
                .header("Authorization", authorizationHeader)
                .GET()
                .build();

        log.debug("Fetching chat stats from chat service: tenant_id={}", tenantId);

        HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            log.error("Chat service returned status {}: {}", response.statusCode(), response.body());
            throw new RuntimeException(
                String.format("Failed to fetch chat stats: HTTP %d - %s",
                    response.statusCode(), response.body())
            );
        }

        log.debug("Successfully retrieved chat stats from chat service");
        return objectMapper.readValue(response.body(), java.util.Map.class);
    }

    /**
     * Check if the chat service is available
     *
     * @return true if the service is reachable, false otherwise
     */
    public boolean isChatServiceAvailable() {
        try {
            String url = chatServiceUrl + "/health";

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(5))
                    .GET()
                    .build();

            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            return response.statusCode() == 200;

        } catch (Exception e) {
            log.warn("Chat service health check failed: {}", e.getMessage());
            return false;
        }
    }
}

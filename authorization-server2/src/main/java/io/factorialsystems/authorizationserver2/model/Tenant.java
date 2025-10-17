package io.factorialsystems.authorizationserver2.model;

import com.fasterxml.jackson.databind.JsonNode;
import lombok.*;

import java.time.OffsetDateTime;

@Getter
@Setter
@ToString
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Tenant {
    private String id;
    private String name;
    private String domain;
    
    // Additional fields to match onboarding service
    private String apiKey;
    private JsonNode config; // JSON configuration as JsonNode
    private String planId;
    private String subscriptionId; // Billing service subscription ID

    private Boolean isActive;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
}
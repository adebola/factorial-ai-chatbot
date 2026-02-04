package io.factorialsystems.authorizationserver2.dto;

import com.fasterxml.jackson.databind.JsonNode;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Request DTO for updating tenant information by system admin
 */
@Getter
@Setter
@NoArgsConstructor
public class UpdateTenantRequest {
    private String name;
    private String domain;
    private JsonNode config;
    private String planId;
}

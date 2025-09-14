package io.factorialsystems.authorizationserver2.dto;

import com.fasterxml.jackson.databind.JsonNode;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
public class TenantConfigUpdateRequest {
    private JsonNode config;
}
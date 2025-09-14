package io.factorialsystems.authorizationserver2.model;

import lombok.*;

import java.time.OffsetDateTime;

@Getter
@Setter
@ToString
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class RegisteredClient {
    private String id;
    private String clientId;
    private String clientSecret;
    private String clientName;
    private String clientAuthenticationMethods; // JSON array
    private String authorizationGrantTypes; // JSON array
    private String redirectUris; // JSON array
    private String postLogoutRedirectUris; // JSON array
    private String scopes; // JSON array
    private String clientSettings; // JSON object
    private String tokenSettings; // JSON object
    private Boolean requireAuthorizationConsent;
    private Boolean requireProofKey;
    private Boolean isActive;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
    
}
package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.mapper.RegisteredClientMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class DatabaseRegisteredClientRepository implements RegisteredClientRepository {

    private final RegisteredClientMapper registeredClientMapper;
    private final ObjectMapper objectMapper;

    @Override
    @Cacheable(value = "registeredClients", key = "#id")
    public RegisteredClient findById(String id) {
        log.debug("Finding registered client by id: {}", id);
        
        io.factorialsystems.authorizationserver2.model.RegisteredClient dbClient = 
                registeredClientMapper.findById(id);
                
        if (dbClient == null) {
            log.debug("No registered client found with id: {}", id);
            return null;
        }
        
        return convertToSpringRegisteredClient(dbClient);
    }

    @Override
    @Cacheable(value = "registeredClientsByClientId", key = "#clientId")
    public RegisteredClient findByClientId(String clientId) {
        log.debug("Finding registered client by clientId: {}", clientId);
        
        io.factorialsystems.authorizationserver2.model.RegisteredClient dbClient = 
                registeredClientMapper.findByClientId(clientId);
                
        if (dbClient == null) {
            log.debug("No registered client found with clientId: {}", clientId);
            return null;
        }
        
        log.debug("Found registered client: {} for clientId: {}", dbClient.getClientName(), clientId);
        return convertToSpringRegisteredClient(dbClient);
    }

    @Override
    public void save(RegisteredClient registeredClient) {
        log.debug("Saving registered client: {}", registeredClient.getClientId());
        
        io.factorialsystems.authorizationserver2.model.RegisteredClient existing = 
                registeredClientMapper.findByClientId(registeredClient.getClientId());
                
        io.factorialsystems.authorizationserver2.model.RegisteredClient dbClient = 
                convertToDbRegisteredClient(registeredClient);
        
        if (existing != null) {
            dbClient.setId(existing.getId());
            dbClient.setCreatedAt(existing.getCreatedAt());
            registeredClientMapper.update(dbClient);
            log.debug("Updated existing registered client: {}", registeredClient.getClientId());
        } else {
            registeredClientMapper.insert(dbClient);
            log.debug("Inserted new registered client: {}", registeredClient.getClientId());
        }
    }

    private RegisteredClient convertToSpringRegisteredClient(
            io.factorialsystems.authorizationserver2.model.RegisteredClient dbClient) {
        
        try {
            RegisteredClient.Builder builder = RegisteredClient.withId(dbClient.getId())
                    .clientId(dbClient.getClientId())
                    .clientName(dbClient.getClientName())
                    .clientSecret(dbClient.getClientSecret());

            // Parse client authentication methods
            List<String> authMethods = objectMapper.readValue(
                    dbClient.getClientAuthenticationMethods(), 
                    new TypeReference<List<String>>() {}
            );
            
            authMethods.forEach(method -> {
                if ("client_secret_basic".equals(method)) {
                    builder.clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC);
                } else if ("client_secret_post".equals(method)) {
                    builder.clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_POST);
                } else if ("client_secret_jwt".equals(method)) {
                    builder.clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_JWT);
                } else if ("private_key_jwt".equals(method)) {
                    builder.clientAuthenticationMethod(ClientAuthenticationMethod.PRIVATE_KEY_JWT);
                } else if ("none".equals(method)) {
                    builder.clientAuthenticationMethod(ClientAuthenticationMethod.NONE);
                }
            });

            // Parse authorization grant types
            List<String> grantTypes = objectMapper.readValue(
                    dbClient.getAuthorizationGrantTypes(), 
                    new TypeReference<List<String>>() {}
            );
            
            grantTypes.forEach(grantType -> {
                if ("authorization_code".equals(grantType)) {
                    builder.authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE);
                } else if ("refresh_token".equals(grantType)) {
                    builder.authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN);
                } else if ("client_credentials".equals(grantType)) {
                    builder.authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS);
                }
            });

            // Parse redirect URIs
            if (dbClient.getRedirectUris() != null) {
                List<String> redirectUris = objectMapper.readValue(
                        dbClient.getRedirectUris(), 
                        new TypeReference<List<String>>() {}
                );
                builder.redirectUris(uris -> uris.addAll(redirectUris));
            }

            // Parse post logout redirect URIs
            if (dbClient.getPostLogoutRedirectUris() != null) {
                List<String> postLogoutUris = objectMapper.readValue(
                        dbClient.getPostLogoutRedirectUris(), 
                        new TypeReference<List<String>>() {}
                );
                builder.postLogoutRedirectUris(uris -> uris.addAll(postLogoutUris));
            }

            // Parse scopes
            List<String> scopes = objectMapper.readValue(
                    dbClient.getScopes(), 
                    new TypeReference<List<String>>() {}
            );
            builder.scopes(scopeSet -> scopeSet.addAll(scopes));

            // Parse client settings
            ClientSettings.Builder clientSettingsBuilder = ClientSettings.builder();
            if (dbClient.getRequireAuthorizationConsent() != null) {
                clientSettingsBuilder.requireAuthorizationConsent(dbClient.getRequireAuthorizationConsent());
            }
            if (dbClient.getRequireProofKey() != null) {
                clientSettingsBuilder.requireProofKey(dbClient.getRequireProofKey());
            }
            builder.clientSettings(clientSettingsBuilder.build());

            // Parse token settings
            TokenSettings.Builder tokenSettingsBuilder = TokenSettings.builder();
            if (dbClient.getTokenSettings() != null && !dbClient.getTokenSettings().isEmpty()) {
                @SuppressWarnings("unchecked")
                var tokenSettingsMap = objectMapper.readValue(
                        dbClient.getTokenSettings(), 
                        new TypeReference<java.util.Map<String, Object>>() {}
                );
                
                if (tokenSettingsMap.containsKey("accessTokenTimeToLive")) {
                    String duration = (String) tokenSettingsMap.get("accessTokenTimeToLive");
                    tokenSettingsBuilder.accessTokenTimeToLive(Duration.parse(duration));
                }
                if (tokenSettingsMap.containsKey("refreshTokenTimeToLive")) {
                    String duration = (String) tokenSettingsMap.get("refreshTokenTimeToLive");
                    tokenSettingsBuilder.refreshTokenTimeToLive(Duration.parse(duration));
                }
            }
            builder.tokenSettings(tokenSettingsBuilder.build());

            return builder.build();
            
        } catch (JsonProcessingException e) {
            log.error("Error parsing JSON fields for registered client: {}", dbClient.getClientId(), e);
            throw new RuntimeException("Failed to parse registered client data", e);
        }
    }

    private io.factorialsystems.authorizationserver2.model.RegisteredClient convertToDbRegisteredClient(
            RegisteredClient springClient) {
        
        try {
            io.factorialsystems.authorizationserver2.model.RegisteredClient dbClient = 
                    io.factorialsystems.authorizationserver2.model.RegisteredClient.builder()
                    .id(springClient.getId())
                    .clientId(springClient.getClientId())
                    .clientSecret(springClient.getClientSecret())
                    .clientName(springClient.getClientName())
                    .build();

            // Convert client authentication methods
            Set<String> authMethods = springClient.getClientAuthenticationMethods().stream()
                    .map(ClientAuthenticationMethod::getValue)
                    .collect(Collectors.toSet());
            dbClient.setClientAuthenticationMethods(objectMapper.writeValueAsString(authMethods));

            // Convert authorization grant types
            Set<String> grantTypes = springClient.getAuthorizationGrantTypes().stream()
                    .map(AuthorizationGrantType::getValue)
                    .collect(Collectors.toSet());
            dbClient.setAuthorizationGrantTypes(objectMapper.writeValueAsString(grantTypes));

            // Convert redirect URIs
            dbClient.setRedirectUris(objectMapper.writeValueAsString(springClient.getRedirectUris()));

            // Convert post logout redirect URIs
            dbClient.setPostLogoutRedirectUris(objectMapper.writeValueAsString(springClient.getPostLogoutRedirectUris()));

            // Convert scopes
            dbClient.setScopes(objectMapper.writeValueAsString(springClient.getScopes()));

            // Convert client settings
            ClientSettings clientSettings = springClient.getClientSettings();
            dbClient.setRequireAuthorizationConsent(clientSettings.isRequireAuthorizationConsent());
            dbClient.setRequireProofKey(clientSettings.isRequireProofKey());
            dbClient.setClientSettings("{}"); // Store as empty JSON for now

            // Convert token settings
            TokenSettings tokenSettings = springClient.getTokenSettings();
            var tokenSettingsMap = new java.util.HashMap<String, Object>();
            tokenSettingsMap.put("accessTokenTimeToLive", tokenSettings.getAccessTokenTimeToLive().toString());
            tokenSettingsMap.put("refreshTokenTimeToLive", tokenSettings.getRefreshTokenTimeToLive().toString());
            dbClient.setTokenSettings(objectMapper.writeValueAsString(tokenSettingsMap));

            dbClient.setIsActive(true);
            dbClient.setCreatedAt(java.time.OffsetDateTime.now());
            dbClient.setUpdatedAt(java.time.OffsetDateTime.now());

            return dbClient;
            
        } catch (JsonProcessingException e) {
            log.error("Error converting SpringRegisteredClient to database format: {}", springClient.getClientId(), e);
            throw new RuntimeException("Failed to convert registered client data", e);
        }
    }
}
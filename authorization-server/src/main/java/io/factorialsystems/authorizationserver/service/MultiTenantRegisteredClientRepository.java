package io.factorialsystems.authorizationserver.service;

import io.factorialsystems.authorizationserver.mapper.TenantMapper;
import io.factorialsystems.authorizationserver.model.Tenant;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.stereotype.Repository;

import java.time.Duration;
import java.util.Optional;
import java.util.Set;

/**
 * Multi-tenant implementation of RegisteredClientRepository.
 * Maps tenant configurations to OAuth2 RegisteredClient objects for Spring Authorization Server.
 */
@Slf4j
@Repository
@RequiredArgsConstructor
public class MultiTenantRegisteredClientRepository implements RegisteredClientRepository {
    
    private final TenantMapper tenantMapper;
    
    @Override
    public void save(RegisteredClient registeredClient) {
        // In our multi-tenant system, clients are managed through tenant CRUD operations
        // This method would typically be called during tenant registration
        throw new UnsupportedOperationException("Client registration is managed through tenant operations");
    }
    
    @Override
    public RegisteredClient findById(String id) {
        log.debug("Finding registered client by ID: {}", id);
        
        try {
            // In our system, the registered client ID is the tenant's client_id
            return findByClientId(id);
        } catch (Exception e) {
            log.error("Error finding registered client by ID: {}", id, e);
            return null;
        }
    }
    
    @Override
    public RegisteredClient findByClientId(String clientId) {
        log.info("Finding registered client by client ID: {}", clientId);
        
        try {
            Optional<Tenant> tenantOpt = tenantMapper.findByClientId(clientId);
            if (tenantOpt.isEmpty()) {
                log.debug("No tenant found for client ID: {}", clientId);
                return null;
            }
            
            Tenant tenant = tenantOpt.get();
            if (tenant.getIsActive() == null || !tenant.getIsActive()) {
                log.debug("Tenant is not active for client ID: {}", clientId);
                return null;
            }
            
            return buildRegisteredClient(tenant);
            
        } catch (Exception e) {
            log.error("Error finding registered client by client ID: {}", clientId, e);
            return null;
        }
    }
    
    /**
     * Build RegisteredClient from Tenant configuration
     */
    private RegisteredClient buildRegisteredClient(Tenant tenant) {
        log.debug("Building RegisteredClient for tenant: {} ({})", tenant.getName(), tenant.getId());
        
        RegisteredClient.Builder builder = RegisteredClient.withId(tenant.getClientId())
                .clientId(tenant.getClientId())
                .clientSecret(tenant.getClientSecret())
                
                // Client authentication methods
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_POST)
                
                // Authorization grant types
                .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
                .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
                
                // Redirect URIs from tenant configuration
                .redirectUris(uris -> {
                    if (tenant.getCallbackUrls() != null) {
                        uris.addAll(tenant.getCallbackUrls());
                    }
                })
                
                // Post logout redirect URIs (for OIDC logout)
                .postLogoutRedirectUris(uris -> {
                    if (tenant.getCallbackUrls() != null) {
                        // Allow logout redirects to the same URIs as login redirects
                        uris.addAll(tenant.getCallbackUrls());
                    }
                })
                
                // Scopes from tenant configuration
                .scopes(scopes -> {
                    if (tenant.getAllowedScopes() != null) {
                        scopes.addAll(tenant.getAllowedScopes());
                    } else {
                        // Default scopes
                        scopes.add(OidcScopes.OPENID);
                        scopes.add(OidcScopes.PROFILE);
                        scopes.add("documents:read");
                        scopes.add("chat:access");
                    }
                })
                
                // Client settings
                .clientSettings(buildClientSettings(tenant))
                
                // Token settings
                .tokenSettings(buildTokenSettings(tenant));
        
        RegisteredClient client = builder.build();
        
        log.debug("Built RegisteredClient for tenant {}: scopes={}, redirectUris={}", 
                tenant.getName(), 
                client.getScopes().size(), 
                client.getRedirectUris().size());
        
        return client;
    }
    
    /**
     * Build client settings for the tenant
     */
    private ClientSettings buildClientSettings(Tenant tenant) {
        return ClientSettings.builder()
                // Require authorization consent for new scopes
                .requireAuthorizationConsent(true)
                
                // Require Proof Key for Code Exchange (PKCE) for public clients
                .requireProofKey(false) // Set to true for public clients
                
                // Client name for the consent screen
                .setting("client.display-name", tenant.getName())
                
                // Tenant-specific settings
                .setting("tenant.id", tenant.getId())
                .setting("tenant.domain", tenant.getDomain())
                .setting("tenant.name", tenant.getName())
                
                .build();
    }
    
    /**
     * Build token settings for the tenant
     */
    private TokenSettings buildTokenSettings(Tenant tenant) {
        return TokenSettings.builder()
                // Access token time-to-live
                .accessTokenTimeToLive(Duration.ofHours(1))
                
                // Refresh token time-to-live
                .refreshTokenTimeToLive(Duration.ofDays(30))
                
                // Reuse refresh tokens
                .reuseRefreshTokens(true)
                
                // Authorization code time-to-live
                .authorizationCodeTimeToLive(Duration.ofMinutes(10))

                .build();
    }
    
    /**
     * Find RegisteredClient by tenant ID (utility method)
     */
    public RegisteredClient findByTenantId(String tenantId) {
        log.debug("Finding registered client by tenant ID: {}", tenantId);
        
        try {
            Optional<Tenant> tenantOpt = tenantMapper.findById(tenantId);
            if (tenantOpt.isEmpty()) {
                log.debug("No tenant found for ID: {}", tenantId);
                return null;
            }
            
            Tenant tenant = tenantOpt.get();
            if (!tenant.getIsActive()) {
                log.debug("Tenant is not active: {}", tenantId);
                return null;
            }
            
            return buildRegisteredClient(tenant);
            
        } catch (Exception e) {
            log.error("Error finding registered client by tenant ID: {}", tenantId, e);
            return null;
        }
    }
    
    /**
     * Get all allowed redirect URIs for a client
     */
    public Set<String> getAllowedRedirectUris(String clientId) {
        RegisteredClient client = findByClientId(clientId);
        return client != null ? client.getRedirectUris() : Set.of();
    }
    
    /**
     * Get all allowed scopes for a client
     */
    public Set<String> getAllowedScopes(String clientId) {
        RegisteredClient client = findByClientId(clientId);
        return client != null ? client.getScopes() : Set.of();
    }
    
    /**
     * Validate if redirect URI is allowed for client
     */
    public boolean isRedirectUriAllowed(String clientId, String redirectUri) {
        RegisteredClient client = findByClientId(clientId);
        return client != null && client.getRedirectUris().contains(redirectUri);
    }
    
    /**
     * Validate if scope is allowed for client
     */
    public boolean isScopeAllowed(String clientId, String scope) {
        RegisteredClient client = findByClientId(clientId);
        return client != null && client.getScopes().contains(scope);
    }
    
    /**
     * Get client authentication methods for a client
     */
    public Set<ClientAuthenticationMethod> getClientAuthenticationMethods(String clientId) {
        RegisteredClient client = findByClientId(clientId);
        return client != null ? client.getClientAuthenticationMethods() : Set.of();
    }
    
    /**
     * Get authorization grant types for a client
     */
    public Set<AuthorizationGrantType> getAuthorizationGrantTypes(String clientId) {
        RegisteredClient client = findByClientId(clientId);
        return client != null ? client.getAuthorizationGrantTypes() : Set.of();
    }
    
    /**
     * Check if client supports authorization code flow
     */
    public boolean supportsAuthorizationCodeGrant(String clientId) {
        return getAuthorizationGrantTypes(clientId).contains(AuthorizationGrantType.AUTHORIZATION_CODE);
    }
    
    /**
     * Check if client supports client credentials flow
     */
    public boolean supportsClientCredentialsGrant(String clientId) {
        return getAuthorizationGrantTypes(clientId).contains(AuthorizationGrantType.CLIENT_CREDENTIALS);
    }
    
    /**
     * Check if client supports refresh token flow
     */
    public boolean supportsRefreshTokenGrant(String clientId) {
        return getAuthorizationGrantTypes(clientId).contains(AuthorizationGrantType.REFRESH_TOKEN);
    }
    
    /**
     * Get tenant information for a client (for JWT claims)
     */
    public Optional<Tenant> getTenantForClient(String clientId) {
        try {
            return tenantMapper.findByClientId(clientId);
        } catch (Exception e) {
            log.error("Error getting tenant for client: {}", clientId, e);
            return Optional.empty();
        }
    }
    
    /**
     * Refresh client configuration (useful after tenant updates)
     */
    public void invalidateClientCache(String clientId) {
        // In a production system, you might implement caching and cache invalidation here
        log.debug("Client cache invalidation requested for: {}", clientId);
    }
    
    /**
     * Get client display name for consent screen
     */
    public String getClientDisplayName(String clientId) {
        RegisteredClient client = findByClientId(clientId);
        if (client != null) {
            Object displayName = client.getClientSettings().getSetting("client.display-name");
            return displayName != null ? displayName.toString() : clientId;
        }
        return clientId;
    }
}
package io.factorialsystems.authorizationserver.service;

import io.factorialsystems.authorizationserver.mapper.TenantMapper;
import io.factorialsystems.authorizationserver.model.Tenant;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.Optional;

/**
 * Service for tenant lookup operations.
 * Supports OAuth2 client-to-tenant mapping and API key resolution.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TenantResolutionService {
    
    private final TenantMapper tenantMapper;
    
    
    /**
     * Resolve tenant by OAuth2 client ID
     */
    public String resolveTenantByClientId(String clientId) {
        try {
            Optional<Tenant> tenant = tenantMapper.findByClientId(clientId);
            return tenant.map(Tenant::getId).orElse(null);
        } catch (Exception e) {
            log.error("Error resolving tenant by client ID: {}", clientId, e);
            return null;
        }
    }
    
    /**
     * Resolve tenant by domain name
     */
    public String resolveTenantByDomain(String domain) {
        try {
            Optional<Tenant> tenant = tenantMapper.findByDomain(domain);
            return tenant.map(Tenant::getId).orElse(null);
        } catch (Exception e) {
            log.error("Error resolving tenant by domain: {}", domain, e);
            return null;
        }
    }
    
    /**
     * Resolve tenant by API key (for WebSocket authentication)
     */
    public String resolveTenantByApiKey(String apiKey) {
        try {
            Optional<Tenant> tenant = tenantMapper.findByApiKey(apiKey);
            return tenant.map(Tenant::getId).orElse(null);
        } catch (Exception e) {
            log.error("Error resolving tenant by API key", e);
            return null;
        }
    }
    
    /**
     * Get tenant object by ID
     */
    public Optional<Tenant> getTenantById(String tenantId) {
        try {
            return tenantMapper.findById(tenantId);
        } catch (Exception e) {
            log.error("Error getting tenant by ID: {}", tenantId, e);
            return Optional.empty();
        }
    }
}
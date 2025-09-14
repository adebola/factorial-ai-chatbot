package io.factorialsystems.authorizationserver.service;

import io.factorialsystems.authorizationserver.dto.TenantCreateRequest;
import io.factorialsystems.authorizationserver.dto.TenantResponse;
import io.factorialsystems.authorizationserver.mapper.*;
import io.factorialsystems.authorizationserver.model.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Service for tenant management operations
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class TenantService {
    
    private final TenantMapper tenantMapper;
    private final UserMapper userMapper;
    private final RoleMapper roleMapper;
    private final UserRoleMapper userRoleMapper;
    private final AuditLogMapper auditLogMapper;
    private final PasswordEncoder passwordEncoder;
    
    /**
     * Create a new tenant with admin user
     */
    @Transactional
    public TenantResponse createTenant(TenantCreateRequest request) {
        log.info("Creating new tenant: {}", request.getName());
        
        try {
            // Validate domain uniqueness
            if (tenantMapper.existsByDomain(request.getDomain())) {
                throw new IllegalArgumentException("Domain already exists: " + request.getDomain());
            }
            
            // Generate unique IDs
            String tenantId = UUID.randomUUID().toString();
            String clientId = generateClientId(tenantId);
            String clientSecret = generateClientSecret();
            String apiKey = generateApiKey();
            
            // Validate client ID uniqueness
            if (tenantMapper.existsByClientId(clientId)) {
                throw new IllegalStateException("Generated client ID already exists, please retry");
            }
            
            // Create tenant
            Tenant tenant = Tenant.builder()
                    .id(tenantId)
                    .name(request.getName())
                    .domain(request.getDomain())
                    .clientId(clientId)
                    .clientSecret(passwordEncoder.encode(clientSecret))
                    .callbackUrls(request.getCallbackUrls() != null ? request.getCallbackUrls() : getDefaultCallbackUrls())
                    .allowedScopes(request.getAllowedScopes() != null ? request.getAllowedScopes() : getDefaultScopes())
                    .isActive(true)
                    .planId(request.getPlanId())
                    .apiKey(apiKey)
                    .createdAt(LocalDateTime.now())
                    .updatedAt(LocalDateTime.now())
                    .build();
            
            int tenantRows = tenantMapper.insertTenant(tenant);
            if (tenantRows == 0) {
                throw new RuntimeException("Failed to create tenant");
            }
            
            // Create tenant-specific roles from templates
            createTenantRoles(tenantId);
            
            // Create admin user
            User adminUser = createAdminUser(request, tenantId);
            
            // Assign admin role to user
            assignTenantAdminRole(adminUser.getId(), tenantId);
            
            // Log tenant creation
            logTenantCreation(tenantId, adminUser.getId());
            
            log.info("Successfully created tenant: {} with ID: {}", request.getName(), tenantId);
            
            return buildTenantResponse(tenant);
            
        } catch (Exception e) {
            log.error("Error creating tenant: {}", request.getName(), e);
            throw new RuntimeException("Failed to create tenant: " + e.getMessage(), e);
        }
    }
    
    /**
     * Get tenant by ID
     */
    @Transactional(readOnly = true)
    public Optional<TenantResponse> getTenantById(String tenantId) {
        try {
            Optional<Tenant> tenantOpt = tenantMapper.findById(tenantId);
            if (tenantOpt.isEmpty()) {
                return Optional.empty();
            }
            
            return Optional.of(buildTenantResponse(tenantOpt.get()));
        } catch (Exception e) {
            log.error("Error getting tenant by ID: {}", tenantId, e);
            return Optional.empty();
        }
    }
    
    /**
     * List all active tenants (admin function)
     */
    @Transactional(readOnly = true)
    public List<TenantResponse> getAllTenants() {
        try {
            List<Tenant> tenants = tenantMapper.findAllActive();
            return tenants.stream()
                    .map(this::buildTenantResponse)
                    .collect(Collectors.toList());
        } catch (Exception e) {
            log.error("Error getting all tenants", e);
            return List.of();
        }
    }
    
    /**
     * Update tenant
     */
    @Transactional
    public Optional<TenantResponse> updateTenant(String tenantId, TenantCreateRequest request) {
        log.info("Updating tenant: {}", tenantId);
        
        try {
            Optional<Tenant> tenantOpt = tenantMapper.findById(tenantId);
            if (tenantOpt.isEmpty()) {
                return Optional.empty();
            }
            
            Tenant tenant = tenantOpt.get();
            
            // Update fields
            tenant.setName(request.getName());
            tenant.setCallbackUrls(request.getCallbackUrls() != null ? request.getCallbackUrls() : tenant.getCallbackUrls());
            tenant.setAllowedScopes(request.getAllowedScopes() != null ? request.getAllowedScopes() : tenant.getAllowedScopes());
            tenant.setPlanId(request.getPlanId());
            
            int rows = tenantMapper.updateTenant(tenant);
            if (rows == 0) {
                throw new RuntimeException("Failed to update tenant");
            }
            
            log.info("Successfully updated tenant: {}", tenantId);
            return Optional.of(buildTenantResponse(tenant));
            
        } catch (Exception e) {
            log.error("Error updating tenant: {}", tenantId, e);
            throw new RuntimeException("Failed to update tenant: " + e.getMessage(), e);
        }
    }
    
    /**
     * Deactivate tenant
     */
    @Transactional
    public boolean deactivateTenant(String tenantId) {
        log.info("Deactivating tenant: {}", tenantId);
        
        try {
            int rows = tenantMapper.deactivateTenant(tenantId);
            if (rows > 0) {
                log.info("Successfully deactivated tenant: {}", tenantId);
                return true;
            }
            return false;
        } catch (Exception e) {
            log.error("Error deactivating tenant: {}", tenantId, e);
            return false;
        }
    }
    
    /**
     * No longer needed - we use global roles now.
     * This method is kept for compatibility but does nothing.
     */
    private void createTenantRoles(String tenantId) {
        // With global roles, no tenant-specific roles need to be created
        log.debug("Using global roles - no tenant-specific roles needed for tenant: {}", tenantId);
    }
    
    /**
     * Create admin user for tenant
     */
    private User createAdminUser(TenantCreateRequest request, String tenantId) {
        try {
            String userId = UUID.randomUUID().toString();
            
            User adminUser = User.builder()
                    .id(userId)
                    .tenantId(tenantId)
                    .username(request.getAdminUsername())
                    .email(request.getAdminEmail())
                    .firstName(request.getAdminFirstName())
                    .lastName(request.getAdminLastName())
                    .isActive(true)
                    .isTenantAdmin(true)
                    .emailVerified(request.getAdminPassword() != null) // Verified if password provided
                    .accountLocked(false)
                    .failedLoginAttempts(0)
                    .createdAt(LocalDateTime.now())
                    .updatedAt(LocalDateTime.now())
                    .build();
            
            // Set password or invitation token
            if (request.getAdminPassword() != null && !request.getAdminPassword().trim().isEmpty()) {
                adminUser.setPasswordHash(passwordEncoder.encode(request.getAdminPassword()));
            } else {
                // Create invitation token for email invitation
                String invitationToken = UUID.randomUUID().toString();
                adminUser.setInvitationToken(invitationToken);
                adminUser.setInvitationExpiresAt(LocalDateTime.now().plusDays(7));
                adminUser.setEmailVerified(false);
            }
            
            int rows = userMapper.insertUser(adminUser);
            if (rows == 0) {
                throw new RuntimeException("Failed to create admin user");
            }
            
            log.debug("Created admin user: {} for tenant: {}", request.getAdminUsername(), tenantId);
            return adminUser;
            
        } catch (Exception e) {
            log.error("Error creating admin user for tenant: {}", tenantId, e);
            throw new RuntimeException("Failed to create admin user", e);
        }
    }
    
    /**
     * Assign admin role to user (now global ADMIN role)
     */
    private void assignTenantAdminRole(String userId, String tenantId) {
        try {
            Optional<Role> adminRoleOpt = roleMapper.findByName("ADMIN");
            if (adminRoleOpt.isEmpty()) {
                throw new RuntimeException("ADMIN role not found");
            }
            
            UserRole userRole = UserRole.createPermanent(userId, adminRoleOpt.get().getId(), null);
            userRole.setId(UUID.randomUUID().toString());
            
            int rows = userRoleMapper.insertUserRole(userRole);
            if (rows == 0) {
                throw new RuntimeException("Failed to assign admin role");
            }
            
            log.debug("Assigned TENANT_ADMIN role to user: {} in tenant: {}", userId, tenantId);
            
        } catch (Exception e) {
            log.error("Error assigning admin role to user: {} in tenant: {}", userId, tenantId, e);
            throw new RuntimeException("Failed to assign admin role", e);
        }
    }
    
    /**
     * Build tenant response DTO
     */
    private TenantResponse buildTenantResponse(Tenant tenant) {
        try {
            // Get statistics
            long userCount = userMapper.getActiveUserCount(tenant.getId());
            List<User> admins = userMapper.findTenantAdmins(tenant.getId());
            long roleCount = roleMapper.getActiveRoleCount(); // Global role count since roles are shared
            
            TenantResponse.TenantStats stats = TenantResponse.TenantStats.builder()
                    .userCount(userCount)
                    .activeUserCount(userCount)
                    .adminUserCount((long) admins.size())
                    .roleCount(roleCount)
                    .lastActivity(tenant.getUpdatedAt())
                    .build();
            
            // Build OAuth client info
            TenantResponse.OAuthClientInfo oauthClient = TenantResponse.OAuthClientInfo.builder()
                    .clientId(tenant.getClientId())
                    .grantTypes(List.of("authorization_code", "refresh_token", "client_credentials"))
                    .authenticationMethods(List.of("client_secret_basic", "client_secret_post"))
                    .scopes(tenant.getAllowedScopes())
                    .redirectUris(tenant.getCallbackUrls())
                    .build();
            
            return TenantResponse.builder()
                    .id(tenant.getId())
                    .name(tenant.getName())
                    .domain(tenant.getDomain())
                    .clientId(tenant.getClientId())
                    .callbackUrls(tenant.getCallbackUrls())
                    .allowedScopes(tenant.getAllowedScopes())
                    .isActive(tenant.getIsActive())
                    .planId(tenant.getPlanId())
                    .createdAt(tenant.getCreatedAt())
                    .updatedAt(tenant.getUpdatedAt())
                    .oauthClient(oauthClient)
                    .stats(stats)
                    .build();
                    
        } catch (Exception e) {
            log.error("Error building tenant response for tenant: {}", tenant.getId(), e);
            throw new RuntimeException("Failed to build tenant response", e);
        }
    }
    
    /**
     * Generate OAuth2 client ID for tenant
     */
    private String generateClientId(String tenantId) {
        return String.format("tenant_%s_web", tenantId);
    }
    
    /**
     * Generate OAuth2 client secret
     */
    private String generateClientSecret() {
        return UUID.randomUUID().toString().replace("-", "");
    }
    
    /**
     * Generate API key for WebSocket authentication
     */
    private String generateApiKey() {
        return "fbot_" + UUID.randomUUID().toString().replace("-", "");
    }
    
    /**
     * Get default callback URLs
     */
    private List<String> getDefaultCallbackUrls() {
        return List.of(
            "http://localhost:4200/auth/callback",
            "https://localhost:4200/auth/callback"
        );
    }
    
    /**
     * Get default OAuth2 scopes
     */
    private List<String> getDefaultScopes() {
        return List.of("openid", "profile", "documents:read", "chat:access");
    }
    
    /**
     * Log tenant creation for audit trail
     */
    private void logTenantCreation(String tenantId, String createdBy) {
        try {
            AuditLog auditLog = AuditLog.createTenantCreation(tenantId, createdBy);
            auditLog.setId(UUID.randomUUID().toString());
            auditLogMapper.insertAuditLog(auditLog);
        } catch (Exception e) {
            log.error("Failed to log tenant creation", e);
        }
    }
}
package io.factorialsystems.authorizationserver.service;

import io.factorialsystems.authorizationserver.mapper.RoleMapper;
import io.factorialsystems.authorizationserver.mapper.TenantMapper;
import io.factorialsystems.authorizationserver.mapper.UserMapper;
import io.factorialsystems.authorizationserver.mapper.AuditLogMapper;
import io.factorialsystems.authorizationserver.model.AuditLog;
import io.factorialsystems.authorizationserver.model.Role;
import io.factorialsystems.authorizationserver.model.Tenant;
import io.factorialsystems.authorizationserver.model.User;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import jakarta.servlet.http.HttpServletRequest;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

/**
 * Multi-tenant aware UserDetailsService for Spring Security OAuth2.
 * Supports both strict-multitenant (with tenant context) and loose-multitenant (global auth) patterns.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class MultiTenantUserDetailsService implements UserDetailsService {
    
    private final UserMapper userMapper;
    private final TenantMapper tenantMapper;
    private final RoleMapper roleMapper;
    private final AuditLogMapper auditLogMapper;
    
    @Override
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
        log.debug("Loading user by username: {}", username);
        
        try {
            // Try global authentication first (loose-multitenant pattern)
            // Username is treated as email for global lookup
            return loadUserGlobally(username);
            
        } catch (UsernameNotFoundException e) {
            // Log failed authentication attempt
            logAuthenticationFailure(username, null, "User not found", e.getMessage());
            
            throw e;
        } catch (Exception e) {
            log.error("Error loading user by username: {}", username, e);
            
            // Log failed authentication attempt
            logAuthenticationFailure(username, null, "Error during user lookup", e.getMessage());
            
            throw new UsernameNotFoundException("User not found: " + username, e);
        }
    }
    
    /**
     * Load user globally by email (loose-multitenant authentication)
     * This method looks up users across all tenants using email as the unique identifier
     */
    @Transactional(readOnly = true)
    public UserDetails loadUserGlobally(String emailOrUsername) throws UsernameNotFoundException {
        log.debug("Loading user globally by email/username: {}", emailOrUsername);
        
        try {
            Optional<User> userOpt;
            
            // Try to find by email first (primary method for loose-multitenant)
            if (emailOrUsername.contains("@")) {
                userOpt = userMapper.findByEmailGlobally(emailOrUsername);
            } else {
                // Fallback to username lookup
                userOpt = userMapper.findByUsernameGlobally(emailOrUsername);
            }
            
            if (userOpt.isEmpty()) {
                log.debug("User not found globally: {}", emailOrUsername);
                throw new UsernameNotFoundException("User not found: " + emailOrUsername);
            }
            
            User user = userOpt.get();
            
            // Load tenant to ensure it's active
            Optional<Tenant> tenantOpt = tenantMapper.findById(user.getTenantId());
            if (tenantOpt.isEmpty()) {
                log.warn("Tenant not found for user: {} (tenant: {})", emailOrUsername, user.getTenantId());
                throw new UsernameNotFoundException("User's tenant not found");
            }
            
            Tenant tenant = tenantOpt.get();
            if (tenant.getIsActive() == null || !tenant.getIsActive()) {
                log.warn("Tenant is not active for user: {} (tenant: {})", emailOrUsername, user.getTenantId());
                throw new UsernameNotFoundException("User's tenant not active");
            }
            
            // Validate user can authenticate
            if (user.canAuthenticate()) {
                String reason = getUserInactiveReason(user);
                log.warn("User cannot authenticate: {}, reason: {}", emailOrUsername, reason);
                logAuthenticationFailure(emailOrUsername, user.getTenantId(), reason, null);
                throw new UsernameNotFoundException("User account not available: " + reason);
            }
            
            // Load user roles
            List<Role> roles = roleMapper.findByUserId(user.getId());
            log.debug("Loaded {} roles for user: {}", roles.size(), emailOrUsername);
            
            // Create and return UserDetails
            MultiTenantUserDetails userDetails = new MultiTenantUserDetails(user, tenant, roles);
            
            log.info("Successfully loaded user globally: {} from tenant: {} ({}) with {} authorities", 
                    emailOrUsername, tenant.getName(), tenant.getDomain(), userDetails.getAuthorities().size());
            
            return userDetails;
            
        } catch (UsernameNotFoundException e) {
            throw e; // Re-throw as-is
        } catch (Exception e) {
            log.error("Unexpected error loading user globally: {}", emailOrUsername, e);
            throw new UsernameNotFoundException("Authentication system error", e);
        }
    }
    
    /**
     * Load user with explicit tenant context (used by OAuth2 flows)
     */
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsernameAndTenant(String username, String tenantId) 
            throws UsernameNotFoundException {
        
        log.debug("Loading user by username: {} for tenant: {}", username, tenantId);
        
        try {
            // Load tenant first to ensure it exists and is active
            Optional<Tenant> tenantOpt = tenantMapper.findById(tenantId);
            if (tenantOpt.isEmpty()) {
                log.warn("Tenant not found: {}", tenantId);
                throw new UsernameNotFoundException("Tenant not found");
            }
            
            Tenant tenant = tenantOpt.get();
            if (tenant.getIsActive() == null || !tenant.getIsActive()) {
                log.warn("Tenant is not active: {}", tenantId);
                throw new UsernameNotFoundException("Tenant not active");
            }
            
            // Load user from the tenant
            Optional<User> userOpt = userMapper.findByUsernameAndTenant(username, tenantId);
            if (userOpt.isEmpty()) {
                log.warn("User not found: {} in tenant: {}", username, tenantId);
                logAuthenticationFailure(username, tenantId, "User not found", null);
                throw new UsernameNotFoundException("User not found: " + username);
            }
            
            User user = userOpt.get();
            
            // Validate user can authenticate
            if (user.canAuthenticate()) {
                String reason = getUserInactiveReason(user);
                log.warn("User cannot authenticate: {} in tenant: {}, reason: {}", username, tenantId, reason);
                logAuthenticationFailure(username, tenantId, reason, null);
                throw new UsernameNotFoundException("User account not available: " + reason);
            }
            
            // Load user roles
            List<Role> roles = roleMapper.findByUserId(user.getId());
            log.debug("Loaded {} roles for user: {}", roles.size(), username);
            
            // Create and return UserDetails
            MultiTenantUserDetails userDetails = new MultiTenantUserDetails(user, tenant, roles);
            
            log.info("Successfully loaded user: {} from tenant: {} with {} authorities", 
                    username, tenant.getDomain(), userDetails.getAuthorities().size());
            
            return userDetails;
            
        } catch (UsernameNotFoundException e) {
            throw e; // Re-throw as-is
        } catch (Exception e) {
            log.error("Unexpected error loading user: {} in tenant: {}", username, tenantId, e);
            logAuthenticationFailure(username, tenantId, "System error", e.getMessage());
            throw new UsernameNotFoundException("Authentication system error", e);
        }
    }
    
    /**
     * Load user by user ID (for token validation)
     */
    @Transactional(readOnly = true)
    public Optional<UserDetails> loadUserByUserId(String userId, String tenantId) {
        log.debug("Loading user by ID: {} for tenant: {}", userId, tenantId);
        
        try {
            Optional<User> userOpt = userMapper.findByIdAndTenant(userId, tenantId);
            if (userOpt.isEmpty()) {
                log.debug("User not found by ID: {} in tenant: {}", userId, tenantId);
                return Optional.empty();
            }
            
            User user = userOpt.get();
            if (user.canAuthenticate()) {
                log.debug("User cannot authenticate: {} in tenant: {}", userId, tenantId);
                return Optional.empty();
            }
            
            Optional<Tenant> tenantOpt = tenantMapper.findById(tenantId);
            if (tenantOpt.isEmpty() || !tenantOpt.get().getIsActive()) {
                log.debug("Tenant not found or inactive: {}", tenantId);
                return Optional.empty();
            }
            
            List<Role> roles = roleMapper.findByUserId(user.getId());
            return Optional.of(new MultiTenantUserDetails(user, tenantOpt.get(), roles));
            
        } catch (Exception e) {
            log.error("Error loading user by ID: {} in tenant: {}", userId, tenantId, e);
            return Optional.empty();
        }
    }
    
    /**
     * Load user for OAuth2 client credentials flow (system users)
     */
    @Transactional(readOnly = true)
    public Optional<UserDetails> loadUserForClientCredentials(String clientId) {
        log.debug("Loading user for client credentials: {}", clientId);
        
        try {
            Optional<Tenant> tenantOpt = tenantMapper.findByClientId(clientId);
            if (tenantOpt.isEmpty()) {
                log.debug("Tenant not found for client: {}", clientId);
                return Optional.empty();
            }
            
            Tenant tenant = tenantOpt.get();
            if (!tenant.getIsActive()) {
                log.debug("Tenant not active for client: {}", clientId);
                return Optional.empty();
            }
            
            // For client credentials, find the first tenant admin or create a system user context
            List<User> admins = userMapper.findTenantAdmins(tenant.getId());
            if (admins.isEmpty()) {
                log.debug("No tenant admins found for client: {}", clientId);
                return Optional.empty();
            }
            
            User adminUser = admins.get(0); // Use the first admin for client credentials
            List<Role> roles = roleMapper.findByUserId(adminUser.getId());
            
            return Optional.of(new MultiTenantUserDetails(adminUser, tenant, roles));
            
        } catch (Exception e) {
            log.error("Error loading user for client credentials: {}", clientId, e);
            return Optional.empty();
        }
    }
    
    
    /**
     * Get human-readable reason why user cannot authenticate
     */
    private String getUserInactiveReason(User user) {
        if (user.getIsActive() == null || !user.getIsActive()) {
            return "Account is deactivated";
        }
        if (user.getEmailVerified() == null || !user.getEmailVerified()) {
            return "Email not verified";
        }
        if (user.getAccountLocked() != null && user.getAccountLocked()) {
            return "Account is locked";
        }
        if (!user.isAccountNonExpired()) {
            return "Account has expired";
        }
        if (user.getPasswordHash() == null || user.getPasswordHash().trim().isEmpty()) {
            return "Password not set";
        }
        return "Account not available";
    }
    
    /**
     * Log authentication failure for audit trail
     */
    private void logAuthenticationFailure(String username, String tenantId, String reason, String details) {
        try {
            String ipAddress = getClientIpAddress();
            String userAgent = getUserAgent();
            
            AuditLog auditLog = AuditLog.createLoginFailure(tenantId, username, ipAddress, userAgent, reason);
            if (details != null) {
                auditLog.getAdditionalData().put("error_details", details);
            }
            auditLog.setId(UUID.randomUUID().toString());
            
            auditLogMapper.insertAuditLog(auditLog);
        } catch (Exception e) {
            log.error("Failed to log authentication failure", e);
        }
    }
    
    /**
     * Get client IP address from request
     */
    private String getClientIpAddress() {
        try {
            ServletRequestAttributes attr = (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();
            HttpServletRequest request = attr.getRequest();
            
            String xForwardedFor = request.getHeader("X-Forwarded-For");
            if (xForwardedFor != null && !xForwardedFor.isEmpty()) {
                return xForwardedFor.split(",")[0].trim();
            }
            
            String xRealIp = request.getHeader("X-Real-IP");
            if (xRealIp != null && !xRealIp.isEmpty()) {
                return xRealIp;
            }
            
            return request.getRemoteAddr();
        } catch (Exception e) {
            return "unknown";
        }
    }
    
    /**
     * Get user agent from request
     */
    private String getUserAgent() {
        try {
            ServletRequestAttributes attr = (ServletRequestAttributes) RequestContextHolder.currentRequestAttributes();
            HttpServletRequest request = attr.getRequest();
            return request.getHeader("User-Agent");
        } catch (Exception e) {
            return "unknown";
        }
    }
}
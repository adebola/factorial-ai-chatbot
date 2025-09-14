package io.factorialsystems.authorizationserver.service;

import io.factorialsystems.authorizationserver.model.Role;
import io.factorialsystems.authorizationserver.model.Tenant;
import io.factorialsystems.authorizationserver.model.User;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;

import java.util.Collection;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Multi-tenant aware UserDetails implementation for Spring Security.
 * Includes tenant context and role-based permissions.
 */
public record MultiTenantUserDetails(User user, Tenant tenant, List<Role> roles) implements UserDetails {

    @Override
    public Collection<? extends GrantedAuthority> getAuthorities() {
        Set<GrantedAuthority> authorities = new HashSet<>();

        // Add role-based authorities
        for (Role role : roles) {
            if (role.getIsActive() != null && role.getIsActive()) {
                // Add the role name as an authority (Spring Security convention)
                authorities.add(new SimpleGrantedAuthority("ROLE_" + role.getName()));

                // Add individual permissions as authorities
                if (role.getPermissions() != null) {
                    for (String permission : role.getPermissions()) {
                        authorities.add(new SimpleGrantedAuthority(permission));
                    }
                }
            }
        }

        // Add tenant admin authority if user is tenant admin
        if (user.getIsTenantAdmin() != null && user.getIsTenantAdmin()) {
            authorities.add(new SimpleGrantedAuthority("ROLE_TENANT_ADMIN"));
            authorities.add(new SimpleGrantedAuthority("tenant:admin"));
        }

        return authorities;
    }

    @Override
    public String getPassword() {
        return user.getPasswordHash();
    }

    @Override
    public String getUsername() {
        // For multi-tenant systems, we can use tenant_username format
        // or just username since authentication is tenant-scoped
        return user.getUsername();
    }

    /**
     * Get the fully qualified username including tenant context
     */
    public String getFullyQualifiedUsername() {
        return String.format("%s@%s", user.getUsername(), tenant.getDomain());
    }

    @Override
    public boolean isAccountNonExpired() {
        return user.isAccountNonExpired();
    }

    @Override
    public boolean isAccountNonLocked() {
        return user.isAccountNonLocked();
    }

    @Override
    public boolean isCredentialsNonExpired() {
        return user.isCredentialsNonExpired();
    }

    @Override
    public boolean isEnabled() {
        return user.isEnabled() && (tenant.getIsActive() != null && tenant.getIsActive());
    }

    /**
     * Get the user ID
     */
    public String getUserId() {
        return user.getId();
    }

    /**
     * Get the tenant ID
     */
    public String getTenantId() {
        return user.getTenantId();
    }

    /**
     * Get the tenant domain
     */
    public String getTenantDomain() {
        return tenant.getDomain();
    }

    /**
     * Get the tenant name
     */
    public String getTenantName() {
        return tenant.getName();
    }

    /**
     * Get the user's full name
     */
    public String getFullName() {
        return user.getFullName();
    }

    /**
     * Get the user's email
     */
    public String getEmail() {
        return user.getEmail();
    }

    /**
     * Check if user has a specific permission
     */
    public boolean hasPermission(String permission) {
        return getAuthorities().stream()
                .anyMatch(authority -> authority.getAuthority().equals(permission));
    }

    /**
     * Check if user has any permission that starts with a prefix
     */
    public boolean hasPermissionStartingWith(String prefix) {
        return getAuthorities().stream()
                .anyMatch(authority -> authority.getAuthority().startsWith(prefix));
    }

    /**
     * Check if user has a specific role
     */
    public boolean hasRole(String roleName) {
        return getAuthorities().stream()
                .anyMatch(authority -> authority.getAuthority().equals("ROLE_" + roleName));
    }

    /**
     * Check if user is a tenant administrator
     */
    public boolean isTenantAdmin() {
        return user.getIsTenantAdmin() != null && user.getIsTenantAdmin();
    }

    /**
     * Check if user is a global administrator
     */
    public boolean isGlobalAdmin() {
        return hasRole("GLOBAL_ADMIN");
    }

    /**
     * Check if user belongs to the system tenant (for global operations)
     * Now checks if user has GLOBAL_ADMIN role instead of hardcoded domain
     */
    public boolean isSystemTenant() {
        return hasRole("GLOBAL_ADMIN");
    }

    /**
     * Get all permission strings (for JWT claims or API responses)
     */
    public Set<String> getAllPermissions() {
        Set<String> permissions = new HashSet<>();
        for (GrantedAuthority authority : getAuthorities()) {
            String auth = authority.getAuthority();
            // Exclude ROLE_ prefixed authorities, only include direct permissions
            if (!auth.startsWith("ROLE_")) {
                permissions.add(auth);
            }
        }
        return permissions;
    }

    /**
     * Get all role names (without ROLE_ prefix)
     */
    public Set<String> getAllRoleNames() {
        Set<String> roleNames = new HashSet<>();
        for (GrantedAuthority authority : getAuthorities()) {
            String auth = authority.getAuthority();
            if (auth.startsWith("ROLE_")) {
                roleNames.add(auth.substring(5)); // Remove "ROLE_" prefix
            }
        }
        return roleNames;
    }

    /**
     * Create a simple tenant context string for logging/auditing
     */
    public String getTenantContext() {
        return String.format("[Tenant: %s (%s), User: %s (%s)]",
                tenant.getName(), tenant.getId(),
                user.getUsername(), user.getId());
    }

    @Override
    public String toString() {
        return String.format("MultiTenantUserDetails{username='%s', tenant='%s', enabled=%s, authorities=%d}",
                getUsername(), getTenantDomain(), isEnabled(), getAuthorities().size());
    }
}
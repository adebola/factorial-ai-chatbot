package io.factorialsystems.authorizationserver2.service;

import io.factorialsystems.authorizationserver2.mapper.UserMapper;
import io.factorialsystems.authorizationserver2.model.Role;
import io.factorialsystems.authorizationserver2.model.User;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.Collection;
import java.util.List;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class DatabaseUserDetailsService implements UserDetailsService {

    private final UserMapper userMapper;

    @Override
    @Cacheable(value = "userDetails", key = "#username")
    @Transactional(readOnly = true)
    public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
        log.debug("Loading user details for username: {}", username);
        
        User user = userMapper.findByUsername(username);
        
        if (user == null) {
            log.debug("User not found with username: {}", username);
            throw new UsernameNotFoundException("User not found with username: " + username);
        }
        
        if (!user.getIsActive()) {
            log.debug("User account is disabled: {}", username);
            throw new UsernameNotFoundException("User account is disabled: " + username);
        }
        
        log.debug("Found user: {} with {} roles", username, user.getRoles() != null ? user.getRoles().size() : 0);
        
        // Update last login time asynchronously (optional)
        updateLastLoginAsync(user);
        
        return new CustomUserPrincipal(user);
    }
    
    @Cacheable(value = "userDetailsByEmail", key = "#email")
    @Transactional(readOnly = true)
    public UserDetails loadUserByEmail(String email) throws UsernameNotFoundException {
        log.debug("Loading user details for email: {}", email);
        
        User user = userMapper.findByEmail(email);
        
        if (user == null) {
            log.debug("User not found with email: {}", email);
            throw new UsernameNotFoundException("User not found with email: " + email);
        }
        
        if (!user.getIsActive()) {
            log.debug("User account is disabled for email: {}", email);
            throw new UsernameNotFoundException("User account is disabled: " + email);
        }
        
        log.debug("Found user by email: {} with {} roles", email, user.getRoles() != null ? user.getRoles().size() : 0);
        
        // Update last login time asynchronously (optional)
        updateLastLoginAsync(user);
        
        return new CustomUserPrincipal(user);
    }
    
    private void updateLastLoginAsync(User user) {
        // This could be made async with @Async annotation
        try {
            user.setLastLoginAt(OffsetDateTime.now());
            user.setUpdatedAt(OffsetDateTime.now());
            userMapper.updateLastLogin(user);
            log.debug("Updated last login time for user: {}", user.getUsername());
        } catch (Exception e) {
            log.warn("Failed to update last login time for user: {}", user.getUsername(), e);
        }
    }

    /**
         * Custom UserDetails implementation that includes additional user information
         */
        public record CustomUserPrincipal(User user) implements UserDetails {

        @Override
            public Collection<? extends GrantedAuthority> getAuthorities() {
                if (user.getRoles() == null || user.getRoles().isEmpty()) {
                    return List.of(new SimpleGrantedAuthority("ROLE_USER"));
                }

            return user.getRoles().stream()
                        .filter(Role::getIsActive)
                        .map(role -> new SimpleGrantedAuthority("ROLE_" + role.getName()))
                        .collect(Collectors.toList());
            }

        @Override
            public String getPassword() {
                return user.getPassword();
            }

        @Override
            public String getUsername() {
                return user.getUsername();
            }

        @Override
            public boolean isAccountNonExpired() {
                return true; // We don't track account expiration
            }

        @Override
            public boolean isAccountNonLocked() {
                return true; // We don't track account locking
            }

        @Override
            public boolean isCredentialsNonExpired() {
                return true; // We don't track credential expiration
            }

        @Override
            public boolean isEnabled() {
                return user.getIsActive();
            }

        // Additional getters for accessing user information
            public String getUserId() {
                return user.getId();
            }

        public String getTenantId() {
                return user.getTenantId();
            }

        public String getEmail() {
                return user.getEmail();
            }

        public String getFirstName() {
                return user.getFirstName();
            }

        public String getLastName() {
                return user.getLastName();
            }

        public String getFullName() {
                if (user.getFirstName() != null && user.getLastName() != null) {
                    return user.getFirstName() + " " + user.getLastName();
                } else if (user.getFirstName() != null) {
                    return user.getFirstName();
                } else if (user.getLastName() != null) {
                    return user.getLastName();
                }
                return user.getUsername();
            }

        public boolean isEmailVerified() {
                return user.getIsEmailVerified();
            }

        public List<Role> getRoles() {
                return user.getRoles();
            }

        public String getApiKey() {
                return user.getApiKey();
            }

            @Override
            public String toString() {
                return "CustomUserPrincipal{" +
                        "username='" + user.getUsername() + '\'' +
                        ", email='" + user.getEmail() + '\'' +
                        ", tenantId='" + user.getTenantId() + '\'' +
                        ", roles=" + (user.getRoles() != null ? user.getRoles().size() : 0) +
                        ", enabled=" + user.getIsActive() +
                        '}';
            }
        }
}

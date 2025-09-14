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

import java.util.Collection;
import java.util.List;
import java.util.stream.Collectors;

@Slf4j
@Service
@RequiredArgsConstructor
public class DatabaseUserDetailsService implements UserDetailsService {

    private final UserMapper userMapper;
    private final UserActivityService userActivityService;

    @Override
    @Cacheable(value = "userDetails", key = "#username")
    public UserDetails loadUserByUsername(String username) throws UsernameNotFoundException {
        log.info("Loading user details for username: {}", username);

        User user = userMapper.findByUsername(username);

        if (user == null) {
            log.error("User not found with username: {}", username);
            throw new UsernameNotFoundException("User not found with username: " + username);
        }

        if (!user.getIsActive()) {
            log.error("User account is disabled: {}", username);
            throw new UsernameNotFoundException("User account is disabled: " + username);
        }

        log.info("Found user: {} with {} roles", username, user.getRoles() != null ? user.getRoles().size() : 0);

        // Update the last login time asynchronously (optional)
        userActivityService.updateLastLoginAsync(user);

        return new CustomUserPrincipal(user);
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

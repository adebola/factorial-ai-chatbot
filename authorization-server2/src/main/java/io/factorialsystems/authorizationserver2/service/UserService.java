package io.factorialsystems.authorizationserver2.service;

import io.factorialsystems.authorizationserver2.mapper.UserMapper;
import io.factorialsystems.authorizationserver2.model.User;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class UserService {
    
    private final UserMapper userMapper;
    private final PasswordEncoder passwordEncoder;
    private final RedisCacheService cacheService;
    
    public User findByUsername(String username) {
        // Check cache first
        User cachedUser = cacheService.getCachedUserByUsername(username);
        if (cachedUser != null) {
            return cachedUser;
        }
        
        // Fetch from database and cache
        User user = userMapper.findByUsername(username);
        if (user != null) {
            cacheService.cacheUser(user);
        }
        return user;
    }
    
    public User findByEmail(String email) {
        // Check cache first
        User cachedUser = cacheService.getCachedUserByEmail(email);
        if (cachedUser != null) {
            return cachedUser;
        }
        
        // Fetch from database and cache
        User user = userMapper.findByEmail(email);
        if (user != null) {
            cacheService.cacheUser(user);
        }
        return user;
    }
    
    public User findById(String id) {
        // Check cache first
        User cachedUser = cacheService.getCachedUser(id);
        if (cachedUser != null) {
            return cachedUser;
        }
        
        // Fetch from database and cache
        User user = userMapper.findById(id);
        if (user != null) {
            cacheService.cacheUser(user);
        }
        return user;
    }
    
    @Transactional
    public User createUser(String tenantId, String username, String email, String password, 
                          String firstName, String lastName, boolean isEmailVerified) {
        // Check if user already exists
        if (findByUsername(username) != null) {
            throw new IllegalArgumentException("A user with this username already exists");
        }
        
        if (findByEmail(email) != null) {
            throw new IllegalArgumentException("A user with this email already exists");
        }
        
        // Create new user
        User user = User.builder()
                .id(UUID.randomUUID().toString())
                .tenantId(tenantId)
                .username(username.toLowerCase().trim())
                .email(email.toLowerCase().trim())
                .password(password != null ? passwordEncoder.encode(password) : null)
                .firstName(firstName != null ? firstName.trim() : null)
                .lastName(lastName != null ? lastName.trim() : null)
                .isActive(true)
                .isEmailVerified(isEmailVerified)
                .createdAt(OffsetDateTime.now())
                .updatedAt(OffsetDateTime.now())
                .build();
        
        int result = userMapper.insert(user);
        if (result <= 0) {
            throw new RuntimeException("Failed to create user");
        }
        
        log.info("Created new user: id={}, username={}, email={}, tenant={}", 
                user.getId(), user.getUsername(), user.getEmail(), user.getTenantId());
        
        // Cache the newly created user
        cacheService.cacheUser(user);
        // Invalidate tenant users cache since we added a new user
        cacheService.evictTenantUsers(tenantId);
        
        return user;
    }
    
    @Transactional
    public User createAdminUser(String tenantId, String username, String email, String password,
                               String firstName, String lastName) {
        // Create the user
        User user = createUser(tenantId, username, email, password, firstName, lastName, true);
        
        // Assign tenant admin role
        String tenantAdminRoleId = userMapper.findRoleIdByName("TENANT_ADMIN");
        if (tenantAdminRoleId == null) {
            throw new RuntimeException("TENANT_ADMIN role not found in the system");
        }
        
        int roleResult = userMapper.insertUserRole(user.getId(), tenantAdminRoleId);
        if (roleResult <= 0) {
            throw new RuntimeException("Failed to assign TENANT_ADMIN role to user");
        }
        
        log.info("Created tenant admin user: id={}, username={}, tenant={}", user.getId(), user.getUsername(), user.getTenantId());
        return user;
    }
    
    @Transactional
    public User updateUser(User user) {
        user.setUpdatedAt(OffsetDateTime.now());
        int result = userMapper.update(user);
        if (result <= 0) {
            throw new RuntimeException("Failed to update user");
        }
        
        log.info("Updated user: id={}, username={}, email={}", user.getId(), user.getUsername(), user.getEmail());
        
        // Update cache with new user data
        cacheService.evictUser(user.getId());
        cacheService.cacheUser(user);
        // Also evict tenant users cache since user data changed
        cacheService.evictTenantUsers(user.getTenantId());
        
        return user;
    }
    
    @Transactional
    public void updateLastLogin(String userId) {
        User user = findById(userId);
        if (user != null) {
            user.setLastLoginAt(OffsetDateTime.now());
            user.setUpdatedAt(OffsetDateTime.now());
            userMapper.updateLastLogin(user);
            log.debug("Updated last login for user: {}", userId);
        }
    }
    
    public boolean isUsernameAvailable(String username) {
        return findByUsername(username.toLowerCase().trim()) == null;
    }
    
    public boolean isEmailAvailable(String email) {
        return findByEmail(email.toLowerCase().trim()) == null;
    }
    
    public List<User> findByTenantId(String tenantId) {
        // Check cache first
        List<User> cachedUsers = cacheService.getCachedTenantUsers(tenantId);
        if (cachedUsers != null) {
            return cachedUsers;
        }
        
        // Fetch from database and cache
        List<User> users = userMapper.findByTenantId(tenantId);
        if (users != null && !users.isEmpty()) {
            cacheService.cacheTenantUsers(tenantId, users);
            // Also cache individual users
            users.forEach(cacheService::cacheUser);
        }
        return users;
    }
    
    @Transactional
    public void changePassword(String userId, String currentPassword, String newPassword) {
        User user = findById(userId);
        if (user == null) {
            throw new IllegalArgumentException("User not found");
        }
        
        if (!passwordEncoder.matches(currentPassword, user.getPassword())) {
            throw new IllegalArgumentException("Current password is incorrect");
        }
        
        String encodedNewPassword = passwordEncoder.encode(newPassword);
        user.setPassword(encodedNewPassword);
        user.setUpdatedAt(OffsetDateTime.now());
        
        int result = userMapper.update(user);
        if (result <= 0) {
            throw new RuntimeException("Failed to update password");
        }
        
        log.info("Password changed successfully for user: {}", userId);
        
        // Evict user cache since password changed
        cacheService.evictUser(userId);
    }
}
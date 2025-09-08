package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.model.User;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

import java.time.Duration;
import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class RedisCacheService {
    
    private final RedisTemplate<String, String> redisTemplate;
    private final ObjectMapper objectMapper;
    
    private static final String TENANT_KEY_PREFIX = "tenant:";
    private static final String TENANT_API_KEY_PREFIX = "tenant:api:";
    private static final String TENANT_DOMAIN_PREFIX = "tenant:domain:";
    private static final String USER_KEY_PREFIX = "user:";
    private static final String USER_EMAIL_PREFIX = "user:email:";
    private static final String USER_USERNAME_PREFIX = "user:username:";
    private static final String TENANT_USERS_PREFIX = "tenant:users:";
    
    private static final Duration DEFAULT_TTL = Duration.ofMinutes(30);
    private static final Duration API_KEY_TTL = Duration.ofHours(1);
    
    /**
     * Cache tenant by ID
     */
    public void cacheTenant(Tenant tenant) {
        if (tenant == null) return;
        
        try {
            String tenantJson = objectMapper.writeValueAsString(tenant);
            String key = TENANT_KEY_PREFIX + tenant.getId();
            
            redisTemplate.opsForValue().set(key, tenantJson, DEFAULT_TTL);
            
            // Cache by API key for fast lookups
            if (tenant.getApiKey() != null) {
                String apiKeyKey = TENANT_API_KEY_PREFIX + tenant.getApiKey();
                redisTemplate.opsForValue().set(apiKeyKey, tenant.getId(), API_KEY_TTL);
            }
            
            // Cache by domain for fast lookups
            if (tenant.getDomain() != null) {
                String domainKey = TENANT_DOMAIN_PREFIX + tenant.getDomain().toLowerCase();
                redisTemplate.opsForValue().set(domainKey, tenant.getId(), DEFAULT_TTL);
            }
            
            log.debug("Cached tenant: {} with TTL: {}", tenant.getId(), DEFAULT_TTL);
            
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize tenant for caching: {}", tenant.getId(), e);
        }
    }
    
    /**
     * Get cached tenant by ID
     */
    public Tenant getCachedTenant(String tenantId) {
        if (tenantId == null) return null;
        
        try {
            String key = TENANT_KEY_PREFIX + tenantId;
            String tenantJson = redisTemplate.opsForValue().get(key);
            
            if (tenantJson != null) {
                log.debug("Cache hit for tenant: {}", tenantId);
                return objectMapper.readValue(tenantJson, Tenant.class);
            }
            
            log.debug("Cache miss for tenant: {}", tenantId);
            return null;
            
        } catch (JsonProcessingException e) {
            log.error("Failed to deserialize cached tenant: {}", tenantId, e);
            return null;
        }
    }
    
    /**
     * Get cached tenant by API key
     */
    public Tenant getCachedTenantByApiKey(String apiKey) {
        if (apiKey == null) return null;
        
        try {
            String apiKeyKey = TENANT_API_KEY_PREFIX + apiKey;
            String tenantId = redisTemplate.opsForValue().get(apiKeyKey);
            
            if (tenantId != null) {
                log.debug("Cache hit for tenant API key lookup");
                return getCachedTenant(tenantId);
            }
            
            log.debug("Cache miss for tenant API key lookup");
            return null;
            
        } catch (Exception e) {
            log.error("Failed to get cached tenant by API key", e);
            return null;
        }
    }
    
    /**
     * Get cached tenant by domain
     */
    public Tenant getCachedTenantByDomain(String domain) {
        if (domain == null) return null;
        
        try {
            String domainKey = TENANT_DOMAIN_PREFIX + domain.toLowerCase();
            String tenantId = redisTemplate.opsForValue().get(domainKey);
            
            if (tenantId != null) {
                log.debug("Cache hit for tenant domain lookup: {}", domain);
                return getCachedTenant(tenantId);
            }
            
            log.debug("Cache miss for tenant domain lookup: {}", domain);
            return null;
            
        } catch (Exception e) {
            log.error("Failed to get cached tenant by domain: {}", domain, e);
            return null;
        }
    }
    
    /**
     * Cache user by ID
     */
    public void cacheUser(User user) {
        if (user == null) return;
        
        try {
            String userJson = objectMapper.writeValueAsString(user);
            String key = USER_KEY_PREFIX + user.getId();
            
            redisTemplate.opsForValue().set(key, userJson, DEFAULT_TTL);
            
            // Cache by email for fast lookups
            if (user.getEmail() != null) {
                String emailKey = USER_EMAIL_PREFIX + user.getEmail().toLowerCase();
                redisTemplate.opsForValue().set(emailKey, user.getId(), DEFAULT_TTL);
            }
            
            // Cache by username for fast lookups
            if (user.getUsername() != null) {
                String usernameKey = USER_USERNAME_PREFIX + user.getUsername().toLowerCase();
                redisTemplate.opsForValue().set(usernameKey, user.getId(), DEFAULT_TTL);
            }
            
            log.debug("Cached user: {} with TTL: {}", user.getId(), DEFAULT_TTL);
            
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize user for caching: {}", user.getId(), e);
        }
    }
    
    /**
     * Get cached user by ID
     */
    public User getCachedUser(String userId) {
        if (userId == null) return null;
        
        try {
            String key = USER_KEY_PREFIX + userId;
            String userJson = redisTemplate.opsForValue().get(key);
            
            if (userJson != null) {
                log.debug("Cache hit for user: {}", userId);
                return objectMapper.readValue(userJson, User.class);
            }
            
            log.debug("Cache miss for user: {}", userId);
            return null;
            
        } catch (JsonProcessingException e) {
            log.error("Failed to deserialize cached user: {}", userId, e);
            return null;
        }
    }
    
    /**
     * Get cached user by email
     */
    public User getCachedUserByEmail(String email) {
        if (email == null) return null;
        
        try {
            String emailKey = USER_EMAIL_PREFIX + email.toLowerCase();
            String userId = redisTemplate.opsForValue().get(emailKey);
            
            if (userId != null) {
                log.debug("Cache hit for user email lookup: {}", email);
                return getCachedUser(userId);
            }
            
            log.debug("Cache miss for user email lookup: {}", email);
            return null;
            
        } catch (Exception e) {
            log.error("Failed to get cached user by email: {}", email, e);
            return null;
        }
    }
    
    /**
     * Get cached user by username
     */
    public User getCachedUserByUsername(String username) {
        if (username == null) return null;
        
        try {
            String usernameKey = USER_USERNAME_PREFIX + username.toLowerCase();
            String userId = redisTemplate.opsForValue().get(usernameKey);
            
            if (userId != null) {
                log.debug("Cache hit for user username lookup: {}", username);
                return getCachedUser(userId);
            }
            
            log.debug("Cache miss for user username lookup: {}", username);
            return null;
            
        } catch (Exception e) {
            log.error("Failed to get cached user by username: {}", username, e);
            return null;
        }
    }
    
    /**
     * Cache tenant users list
     */
    public void cacheTenantUsers(String tenantId, List<User> users) {
        if (tenantId == null || users == null) return;
        
        try {
            String usersJson = objectMapper.writeValueAsString(users);
            String key = TENANT_USERS_PREFIX + tenantId;
            
            redisTemplate.opsForValue().set(key, usersJson, Duration.ofMinutes(15));
            log.debug("Cached {} users for tenant: {}", users.size(), tenantId);
            
        } catch (JsonProcessingException e) {
            log.error("Failed to serialize tenant users for caching: {}", tenantId, e);
        }
    }
    
    /**
     * Get cached tenant users list
     */
    public List<User> getCachedTenantUsers(String tenantId) {
        if (tenantId == null) return null;
        
        try {
            String key = TENANT_USERS_PREFIX + tenantId;
            String usersJson = redisTemplate.opsForValue().get(key);
            
            if (usersJson != null) {
                log.debug("Cache hit for tenant users: {}", tenantId);
                return objectMapper.readValue(usersJson, 
                    objectMapper.getTypeFactory().constructCollectionType(List.class, User.class));
            }
            
            log.debug("Cache miss for tenant users: {}", tenantId);
            return null;
            
        } catch (JsonProcessingException e) {
            log.error("Failed to deserialize cached tenant users: {}", tenantId, e);
            return null;
        }
    }
    
    /**
     * Invalidate tenant cache
     */
    public void evictTenant(String tenantId) {
        if (tenantId == null) return;
        
        String key = TENANT_KEY_PREFIX + tenantId;
        redisTemplate.delete(key);
        
        // Also evict tenant users cache
        evictTenantUsers(tenantId);
        
        log.debug("Evicted tenant cache: {}", tenantId);
    }
    
    /**
     * Invalidate user cache
     */
    public void evictUser(String userId) {
        if (userId == null) return;
        
        String key = USER_KEY_PREFIX + userId;
        redisTemplate.delete(key);
        
        log.debug("Evicted user cache: {}", userId);
    }
    
    /**
     * Invalidate tenant users cache
     */
    public void evictTenantUsers(String tenantId) {
        if (tenantId == null) return;
        
        String key = TENANT_USERS_PREFIX + tenantId;
        redisTemplate.delete(key);
        
        log.debug("Evicted tenant users cache: {}", tenantId);
    }
    
    /**
     * Clear all cache entries (use with caution)
     */
    public void clearAllCache() {
        try {
            assert redisTemplate.getConnectionFactory() != null;
            redisTemplate.getConnectionFactory().getConnection().flushAll();
            log.warn("Cleared all Redis cache entries");
        } catch (Exception e) {
            log.error("Failed to clear all cache entries", e);
        }
    }
}
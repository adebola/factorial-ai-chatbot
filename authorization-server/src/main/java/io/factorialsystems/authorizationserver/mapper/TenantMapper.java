package io.factorialsystems.authorizationserver.mapper;

import io.factorialsystems.authorizationserver.model.Tenant;
import org.apache.ibatis.annotations.*;

import java.util.List;
import java.util.Optional;

/**
 * MyBatis mapper for tenant CRUD operations and OAuth2 client management.
 * Handles tenant isolation and multi-tenant OAuth2 client configuration.
 */
@Mapper
public interface TenantMapper {
    
    /**
     * Create a new tenant
     */
    @Insert("""
        INSERT INTO tenants (
            id, name, domain, client_id, client_secret, 
            callback_urls, allowed_scopes, is_active, plan_id, api_key, created_by
        ) VALUES (
            #{id}, #{name}, #{domain}, #{clientId}, #{clientSecret},
            #{callbackUrls,typeHandler=io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler},
            #{allowedScopes,typeHandler=io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler},
            #{isActive}, #{planId}, #{apiKey}, #{createdBy}
        )
    """)
    int insertTenant(Tenant tenant);
    
    /**
     * Update an existing tenant
     */
    @Update("""
        UPDATE tenants SET 
            name = #{name},
            domain = #{domain},
            client_secret = #{clientSecret},
            callback_urls = #{callbackUrls,typeHandler=io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler},
            allowed_scopes = #{allowedScopes,typeHandler=io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler},
            is_active = #{isActive},
            plan_id = #{planId},
            api_key = #{apiKey},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{id}
    """)
    int updateTenant(Tenant tenant);
    
    /**
     * Find tenant by ID
     */
    @Select("""
        SELECT id, name, domain, client_id, client_secret, 
               callback_urls, allowed_scopes, is_active, plan_id, api_key,
               created_at, updated_at, created_by
        FROM tenants 
        WHERE id = #{id}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "clientId", column = "client_id"),
        @Result(property = "clientSecret", column = "client_secret"),
        @Result(property = "callbackUrls", column = "callback_urls", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "allowedScopes", column = "allowed_scopes",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at"),
        @Result(property = "createdBy", column = "created_by")
    })
    Optional<Tenant> findById(String id);
    
    /**
     * Find tenant by domain (for tenant resolution)
     */
    @Select("""
        SELECT id, name, domain, client_id, client_secret, 
               callback_urls, allowed_scopes, is_active, plan_id, api_key,
               created_at, updated_at, created_by
        FROM tenants 
        WHERE domain = #{domain} AND is_active = true
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "clientId", column = "client_id"),
        @Result(property = "clientSecret", column = "client_secret"),
        @Result(property = "callbackUrls", column = "callback_urls", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "allowedScopes", column = "allowed_scopes",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at"),
        @Result(property = "createdBy", column = "created_by")
    })
    Optional<Tenant> findByDomain(String domain);
    
    /**
     * Find tenant by OAuth2 client ID (for OAuth2 flows)
     */
    @Select("""
        SELECT id, name, domain, client_id, client_secret, 
               callback_urls, allowed_scopes, is_active, plan_id, api_key,
               created_at, updated_at, created_by
        FROM tenants 
        WHERE client_id = #{clientId} AND is_active = true
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "clientId", column = "client_id"),
        @Result(property = "clientSecret", column = "client_secret"),
        @Result(property = "callbackUrls", column = "callback_urls", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "allowedScopes", column = "allowed_scopes",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at"),
        @Result(property = "createdBy", column = "created_by")
    })
    Optional<Tenant> findByClientId(String clientId);
    
    /**
     * Find tenant by API key (for WebSocket authentication)
     */
    @Select("""
        SELECT id, name, domain, client_id, client_secret, 
               callback_urls, allowed_scopes, is_active, plan_id, api_key,
               created_at, updated_at, created_by
        FROM tenants 
        WHERE api_key = #{apiKey} AND is_active = true
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "clientId", column = "client_id"),
        @Result(property = "clientSecret", column = "client_secret"),
        @Result(property = "callbackUrls", column = "callback_urls", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "allowedScopes", column = "allowed_scopes",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at"),
        @Result(property = "createdBy", column = "created_by")
    })
    Optional<Tenant> findByApiKey(String apiKey);
    
    /**
     * List all active tenants (admin function)
     */
    @Select("""
        SELECT id, name, domain, client_id, client_secret, 
               callback_urls, allowed_scopes, is_active, plan_id, api_key,
               created_at, updated_at, created_by
        FROM tenants 
        WHERE is_active = true
        ORDER BY created_at DESC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "clientId", column = "client_id"),
        @Result(property = "clientSecret", column = "client_secret"),
        @Result(property = "callbackUrls", column = "callback_urls", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "allowedScopes", column = "allowed_scopes",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.StringArrayTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at"),
        @Result(property = "createdBy", column = "created_by")
    })
    List<Tenant> findAllActive();
    
    /**
     * Check if domain is already taken
     */
    @Select("SELECT COUNT(*) FROM tenants WHERE domain = #{domain}")
    boolean existsByDomain(String domain);
    
    /**
     * Check if client ID is already taken
     */
    @Select("SELECT COUNT(*) FROM tenants WHERE client_id = #{clientId}")
    boolean existsByClientId(String clientId);
    
    /**
     * Check if API key is already taken
     */
    @Select("SELECT COUNT(*) FROM tenants WHERE api_key = #{apiKey}")
    boolean existsByApiKey(String apiKey);
    
    /**
     * Soft delete tenant (deactivate)
     */
    @Update("""
        UPDATE tenants SET 
            is_active = false,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{id}
    """)
    int deactivateTenant(String id);
    
    /**
     * Get tenant count (for admin dashboard)
     */
    @Select("SELECT COUNT(*) FROM tenants WHERE is_active = true")
    long getActiveTenantCount();
    
    /**
     * Update tenant's last activity timestamp (for analytics)
     */
    @Update("""
        UPDATE tenants SET 
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{tenantId}
    """)
    int updateLastActivity(String tenantId);
}
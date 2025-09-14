package io.factorialsystems.authorizationserver2.mapper;

import io.factorialsystems.authorizationserver2.model.TenantSettings;
import org.apache.ibatis.annotations.*;

import java.util.List;

/**
 * MyBatis mapper for tenant settings operations
 */
@Mapper
public interface TenantSettingsMapper {
    
    /**
     * Insert new tenant settings
     */
    @Insert("""
        INSERT INTO tenant_settings (
            id, tenant_id, primary_color, secondary_color, 
            hover_text, welcome_message, chat_window_title,
            company_logo_url, additional_settings, is_active, created_at
        ) VALUES (
            #{id}, #{tenantId}, #{primaryColor}, #{secondaryColor},
            #{hoverText}, #{welcomeMessage}, #{chatWindowTitle},
            #{companyLogoUrl},
            #{additionalSettings, typeHandler=io.factorialsystems.authorizationserver2.typehandler.MapTypeHandler}::json,
            #{isActive}, CURRENT_TIMESTAMP
        )
        """)
    void insert(TenantSettings settings);
    
    /**
     * Find settings by tenant ID
     */
    @Select("""
        SELECT id, tenant_id, primary_color, secondary_color,
               hover_text, welcome_message, chat_window_title,
               company_logo_url, additional_settings, is_active, created_at, updated_at
        FROM tenant_settings 
        WHERE tenant_id = #{tenantId} AND is_active = true
        """)
    @Result(property = "tenantId", column = "tenant_id")
    @Result(property = "primaryColor", column = "primary_color")
    @Result(property = "secondaryColor", column = "secondary_color")
    @Result(property = "hoverText", column = "hover_text")
    @Result(property = "welcomeMessage", column = "welcome_message")
    @Result(property = "chatWindowTitle", column = "chat_window_title")
    @Result(property = "companyLogoUrl", column = "company_logo_url")
    @Result(property = "additionalSettings", column = "additional_settings", 
            typeHandler = io.factorialsystems.authorizationserver2.typehandler.MapTypeHandler.class)
    @Result(property = "isActive", column = "is_active")
    @Result(property = "createdAt", column = "created_at")
    @Result(property = "updatedAt", column = "updated_at")
    TenantSettings findByTenantId(@Param("tenantId") String tenantId);
    
    /**
     * Find settings by ID
     */
    @Select("""
        SELECT id, tenant_id, primary_color, secondary_color,
               hover_text, welcome_message, chat_window_title,
               company_logo_url, additional_settings, is_active, created_at, updated_at
        FROM tenant_settings 
        WHERE id = #{id} AND is_active = true
        """)
    @Result(property = "tenantId", column = "tenant_id")
    @Result(property = "primaryColor", column = "primary_color")
    @Result(property = "secondaryColor", column = "secondary_color")
    @Result(property = "hoverText", column = "hover_text")
    @Result(property = "welcomeMessage", column = "welcome_message")
    @Result(property = "chatWindowTitle", column = "chat_window_title")
    @Result(property = "companyLogoUrl", column = "company_logo_url")
    @Result(property = "additionalSettings", column = "additional_settings",
            typeHandler = io.factorialsystems.authorizationserver2.typehandler.MapTypeHandler.class)
    @Result(property = "isActive", column = "is_active")
    @Result(property = "createdAt", column = "created_at")
    @Result(property = "updatedAt", column = "updated_at")
    TenantSettings findById(@Param("id") String id);
    
    /**
     * Update tenant settings
     */
    @Update("""
        UPDATE tenant_settings 
        SET primary_color = #{primaryColor},
            secondary_color = #{secondaryColor},
            hover_text = #{hoverText},
            welcome_message = #{welcomeMessage},
            chat_window_title = #{chatWindowTitle},
            company_logo_url = #{companyLogoUrl},
            additional_settings = #{additionalSettings, typeHandler=io.factorialsystems.authorizationserver2.typehandler.MapTypeHandler}::json,
            updated_at = CURRENT_TIMESTAMP
        WHERE tenant_id = #{tenantId} AND is_active = true
        """)
    int updateByTenantId(TenantSettings settings);
    
    /**
     * Update tenant logo settings
     */
    @Update("""
        UPDATE tenant_settings 
        SET company_logo_url = #{logoUrl},
            updated_at = CURRENT_TIMESTAMP
        WHERE tenant_id = #{tenantId} AND is_active = true
        """)
    int updateTenantLogo(@Param("tenantId") String tenantId, 
                        @Param("logoUrl") String logoUrl);
    
    /**
     * Soft delete tenant settings
     */
    @Update("""
        UPDATE tenant_settings 
        SET is_active = false, updated_at = CURRENT_TIMESTAMP
        WHERE tenant_id = #{tenantId} AND is_active = true
        """)
    int softDeleteByTenantId(@Param("tenantId") String tenantId);
    
    /**
     * Check if tenant settings exist
     */
    @Select("""
        SELECT COUNT(*) > 0 
        FROM tenant_settings 
        WHERE tenant_id = #{tenantId} AND is_active = true
        """)
    boolean existsByTenantId(@Param("tenantId") String tenantId);
    
    /**
     * Get all tenant settings (admin only)
     */
    @Select("""
        SELECT id, tenant_id, primary_color, secondary_color,
               hover_text, welcome_message, chat_window_title,
               company_logo_url, additional_settings, is_active, created_at, updated_at
        FROM tenant_settings 
        WHERE is_active = true
        ORDER BY created_at DESC
        """)
    @Result(property = "tenantId", column = "tenant_id")
    @Result(property = "primaryColor", column = "primary_color")
    @Result(property = "secondaryColor", column = "secondary_color")
    @Result(property = "hoverText", column = "hover_text")
    @Result(property = "welcomeMessage", column = "welcome_message")
    @Result(property = "chatWindowTitle", column = "chat_window_title")
    @Result(property = "companyLogoUrl", column = "company_logo_url")
    @Result(property = "additionalSettings", column = "additional_settings",
            typeHandler = io.factorialsystems.authorizationserver2.typehandler.MapTypeHandler.class)
    @Result(property = "isActive", column = "is_active")
    @Result(property = "createdAt", column = "created_at")
    @Result(property = "updatedAt", column = "updated_at")
    List<TenantSettings> findAll();
}
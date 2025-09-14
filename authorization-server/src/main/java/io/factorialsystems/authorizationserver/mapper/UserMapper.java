package io.factorialsystems.authorizationserver.mapper;

import io.factorialsystems.authorizationserver.model.User;
import org.apache.ibatis.annotations.*;

import java.util.List;
import java.util.Optional;

/**
 * MyBatis mapper for user CRUD operations.
 * Supports both tenant-scoped queries (strict-multitenant) and global queries (loose-multitenant).
 */
@Mapper
public interface UserMapper {
    
    /**
     * Create a new user
     */
    @Insert("""
        INSERT INTO users (
            id, tenant_id, username, email, password_hash, 
            first_name, last_name, is_active, is_tenant_admin, email_verified,
            account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by
        ) VALUES (
            #{id}, #{tenantId}, #{username}, #{email}, #{passwordHash},
            #{firstName}, #{lastName}, #{isActive}, #{isTenantAdmin}, #{emailVerified},
            #{accountLocked}, #{passwordExpiresAt}, #{invitationToken}, #{invitationExpiresAt}, #{invitedBy}
        )
    """)
    int insertUser(User user);
    
    /**
     * Update an existing user
     */
    @Update("""
        UPDATE users SET 
            username = #{username},
            email = #{email},
            password_hash = #{passwordHash},
            first_name = #{firstName},
            last_name = #{lastName},
            is_active = #{isActive},
            is_tenant_admin = #{isTenantAdmin},
            email_verified = #{emailVerified},
            account_locked = #{accountLocked},
            password_expires_at = #{passwordExpiresAt},
            failed_login_attempts = #{failedLoginAttempts},
            last_failed_login_at = #{lastFailedLoginAt},
            last_login_at = #{lastLoginAt},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{id} AND tenant_id = #{tenantId}
    """)
    int updateUser(User user);
    
    /**
     * Find user by ID with tenant isolation
     */
    @Select("""
        SELECT id, tenant_id, username, email, password_hash,
               first_name, last_name, is_active, is_tenant_admin, email_verified,
               account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by,
               last_login_at, failed_login_attempts, last_failed_login_at,
               created_at, updated_at
        FROM users 
        WHERE id = #{id} AND tenant_id = #{tenantId}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "passwordHash", column = "password_hash"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isTenantAdmin", column = "is_tenant_admin"),
        @Result(property = "emailVerified", column = "email_verified"),
        @Result(property = "accountLocked", column = "account_locked"),
        @Result(property = "passwordExpiresAt", column = "password_expires_at"),
        @Result(property = "invitationToken", column = "invitation_token"),
        @Result(property = "invitationExpiresAt", column = "invitation_expires_at"),
        @Result(property = "invitedBy", column = "invited_by"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "failedLoginAttempts", column = "failed_login_attempts"),
        @Result(property = "lastFailedLoginAt", column = "last_failed_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Optional<User> findByIdAndTenant(String id, String tenantId);
    
    /**
     * Find user by username within tenant (for authentication)
     */
    @Select("""
        SELECT id, tenant_id, username, email, password_hash,
               first_name, last_name, is_active, is_tenant_admin, email_verified,
               account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by,
               last_login_at, failed_login_attempts, last_failed_login_at,
               created_at, updated_at
        FROM users 
        WHERE username = #{username} AND tenant_id = #{tenantId} AND is_active = true
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "passwordHash", column = "password_hash"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isTenantAdmin", column = "is_tenant_admin"),
        @Result(property = "emailVerified", column = "email_verified"),
        @Result(property = "accountLocked", column = "account_locked"),
        @Result(property = "passwordExpiresAt", column = "password_expires_at"),
        @Result(property = "invitationToken", column = "invitation_token"),
        @Result(property = "invitationExpiresAt", column = "invitation_expires_at"),
        @Result(property = "invitedBy", column = "invited_by"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "failedLoginAttempts", column = "failed_login_attempts"),
        @Result(property = "lastFailedLoginAt", column = "last_failed_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Optional<User> findByUsernameAndTenant(String username, String tenantId);
    
    /**
     * Find user by email within tenant
     */
    @Select("""
        SELECT id, tenant_id, username, email, password_hash,
               first_name, last_name, is_active, is_tenant_admin, email_verified,
               account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by,
               last_login_at, failed_login_attempts, last_failed_login_at,
               created_at, updated_at
        FROM users 
        WHERE email = #{email} AND tenant_id = #{tenantId} AND is_active = true
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "passwordHash", column = "password_hash"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isTenantAdmin", column = "is_tenant_admin"),
        @Result(property = "emailVerified", column = "email_verified"),
        @Result(property = "accountLocked", column = "account_locked"),
        @Result(property = "passwordExpiresAt", column = "password_expires_at"),
        @Result(property = "invitationToken", column = "invitation_token"),
        @Result(property = "invitationExpiresAt", column = "invitation_expires_at"),
        @Result(property = "invitedBy", column = "invited_by"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "failedLoginAttempts", column = "failed_login_attempts"),
        @Result(property = "lastFailedLoginAt", column = "last_failed_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Optional<User> findByEmailAndTenant(String email, String tenantId);
    
    // =============================================================================
    // GLOBAL USER LOOKUP METHODS (for loose-multitenant authentication)
    // =============================================================================
    
    /**
     * Find user by email globally (across all tenants) for loose-multitenant authentication
     */
    @Select("""
        SELECT id, tenant_id, username, email, password_hash,
               first_name, last_name, is_active, is_tenant_admin, email_verified,
               account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by,
               last_login_at, failed_login_attempts, last_failed_login_at,
               created_at, updated_at
        FROM users 
        WHERE email = #{email} AND is_active = true
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "passwordHash", column = "password_hash"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isTenantAdmin", column = "is_tenant_admin"),
        @Result(property = "emailVerified", column = "email_verified"),
        @Result(property = "accountLocked", column = "account_locked"),
        @Result(property = "passwordExpiresAt", column = "password_expires_at"),
        @Result(property = "invitationToken", column = "invitation_token"),
        @Result(property = "invitationExpiresAt", column = "invitation_expires_at"),
        @Result(property = "invitedBy", column = "invited_by"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "failedLoginAttempts", column = "failed_login_attempts"),
        @Result(property = "lastFailedLoginAt", column = "last_failed_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Optional<User> findByEmailGlobally(String email);
    
    /**
     * Find user by username globally (across all tenants)
     */
    @Select("""
        SELECT id, tenant_id, username, email, password_hash,
               first_name, last_name, is_active, is_tenant_admin, email_verified,
               account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by,
               last_login_at, failed_login_attempts, last_failed_login_at,
               created_at, updated_at
        FROM users 
        WHERE username = #{username} AND is_active = true
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "passwordHash", column = "password_hash"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isTenantAdmin", column = "is_tenant_admin"),
        @Result(property = "emailVerified", column = "email_verified"),
        @Result(property = "accountLocked", column = "account_locked"),
        @Result(property = "passwordExpiresAt", column = "password_expires_at"),
        @Result(property = "invitationToken", column = "invitation_token"),
        @Result(property = "invitationExpiresAt", column = "invitation_expires_at"),
        @Result(property = "invitedBy", column = "invited_by"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "failedLoginAttempts", column = "failed_login_attempts"),
        @Result(property = "lastFailedLoginAt", column = "last_failed_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Optional<User> findByUsernameGlobally(String username);
    
    /**
     * Check if email exists globally (across all tenants) - for invitation conflict checking
     */
    @Select("SELECT COUNT(*) FROM users WHERE email = #{email}")
    boolean existsByEmailGlobally(String email);
    
    /**
     * Check if username exists globally (across all tenants) - for conflict checking
     */
    @Select("SELECT COUNT(*) FROM users WHERE username = #{username}")
    boolean existsByUsernameGlobally(String username);
    
    /**
     * Generate unique email for invitation using database function
     */
    @Select("SELECT generate_unique_invitation_email(#{originalEmail}, #{tenantDomain})")
    String generateUniqueInvitationEmail(String originalEmail, String tenantDomain);
    
    /**
     * Generate unique username using database function
     */
    @Select("SELECT generate_unique_username(#{originalUsername}, #{tenantDomain})")
    String generateUniqueUsername(String originalUsername, String tenantDomain);
    
    /**
     * Find user by invitation token (for email confirmation)
     */
    @Select("""
        SELECT id, tenant_id, username, email, password_hash,
               first_name, last_name, is_active, is_tenant_admin, email_verified,
               account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by,
               last_login_at, failed_login_attempts, last_failed_login_at,
               created_at, updated_at
        FROM users 
        WHERE invitation_token = #{token} 
          AND invitation_expires_at > CURRENT_TIMESTAMP
          AND is_active = true
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "passwordHash", column = "password_hash"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isTenantAdmin", column = "is_tenant_admin"),
        @Result(property = "emailVerified", column = "email_verified"),
        @Result(property = "accountLocked", column = "account_locked"),
        @Result(property = "passwordExpiresAt", column = "password_expires_at"),
        @Result(property = "invitationToken", column = "invitation_token"),
        @Result(property = "invitationExpiresAt", column = "invitation_expires_at"),
        @Result(property = "invitedBy", column = "invited_by"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "failedLoginAttempts", column = "failed_login_attempts"),
        @Result(property = "lastFailedLoginAt", column = "last_failed_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Optional<User> findByValidInvitationToken(String token);
    
    /**
     * List all users for a tenant
     */
    @Select("""
        SELECT id, tenant_id, username, email, password_hash,
               first_name, last_name, is_active, is_tenant_admin, email_verified,
               account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by,
               last_login_at, failed_login_attempts, last_failed_login_at,
               created_at, updated_at
        FROM users 
        WHERE tenant_id = #{tenantId}
        ORDER BY created_at DESC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "passwordHash", column = "password_hash"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isTenantAdmin", column = "is_tenant_admin"),
        @Result(property = "emailVerified", column = "email_verified"),
        @Result(property = "accountLocked", column = "account_locked"),
        @Result(property = "passwordExpiresAt", column = "password_expires_at"),
        @Result(property = "invitationToken", column = "invitation_token"),
        @Result(property = "invitationExpiresAt", column = "invitation_expires_at"),
        @Result(property = "invitedBy", column = "invited_by"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "failedLoginAttempts", column = "failed_login_attempts"),
        @Result(property = "lastFailedLoginAt", column = "last_failed_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<User> findByTenant(String tenantId);
    
    /**
     * List active users for a tenant
     */
    @Select("""
        SELECT id, tenant_id, username, email, password_hash,
               first_name, last_name, is_active, is_tenant_admin, email_verified,
               account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by,
               last_login_at, failed_login_attempts, last_failed_login_at,
               created_at, updated_at
        FROM users 
        WHERE tenant_id = #{tenantId} AND is_active = true
        ORDER BY created_at DESC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "passwordHash", column = "password_hash"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isTenantAdmin", column = "is_tenant_admin"),
        @Result(property = "emailVerified", column = "email_verified"),
        @Result(property = "accountLocked", column = "account_locked"),
        @Result(property = "passwordExpiresAt", column = "password_expires_at"),
        @Result(property = "invitationToken", column = "invitation_token"),
        @Result(property = "invitationExpiresAt", column = "invitation_expires_at"),
        @Result(property = "invitedBy", column = "invited_by"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "failedLoginAttempts", column = "failed_login_attempts"),
        @Result(property = "lastFailedLoginAt", column = "last_failed_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<User> findActiveByTenant(String tenantId);
    
    /**
     * Find tenant admins for a tenant
     */
    @Select("""
        SELECT id, tenant_id, username, email, password_hash,
               first_name, last_name, is_active, is_tenant_admin, email_verified,
               account_locked, password_expires_at, invitation_token, invitation_expires_at, invited_by,
               last_login_at, failed_login_attempts, last_failed_login_at,
               created_at, updated_at
        FROM users 
        WHERE tenant_id = #{tenantId} AND is_tenant_admin = true AND is_active = true
        ORDER BY created_at ASC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "passwordHash", column = "password_hash"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isTenantAdmin", column = "is_tenant_admin"),
        @Result(property = "emailVerified", column = "email_verified"),
        @Result(property = "accountLocked", column = "account_locked"),
        @Result(property = "passwordExpiresAt", column = "password_expires_at"),
        @Result(property = "invitationToken", column = "invitation_token"),
        @Result(property = "invitationExpiresAt", column = "invitation_expires_at"),
        @Result(property = "invitedBy", column = "invited_by"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "failedLoginAttempts", column = "failed_login_attempts"),
        @Result(property = "lastFailedLoginAt", column = "last_failed_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<User> findTenantAdmins(String tenantId);
    
    /**
     * Check if username exists within tenant
     */
    @Select("SELECT COUNT(*) FROM users WHERE username = #{username} AND tenant_id = #{tenantId}")
    boolean existsByUsernameAndTenant(String username, String tenantId);
    
    /**
     * Check if email exists within tenant
     */
    @Select("SELECT COUNT(*) FROM users WHERE email = #{email} AND tenant_id = #{tenantId}")
    boolean existsByEmailAndTenant(String email, String tenantId);
    
    /**
     * Update user password and clear invitation token
     */
    @Update("""
        UPDATE users SET 
            password_hash = #{passwordHash},
            invitation_token = NULL,
            invitation_expires_at = NULL,
            email_verified = true,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{id} AND tenant_id = #{tenantId}
    """)
    int updatePasswordAndClearInvitation(String id, String tenantId, String passwordHash);
    
    /**
     * Update login tracking information
     */
    @Update("""
        UPDATE users SET 
            last_login_at = #{lastLoginAt},
            failed_login_attempts = #{failedLoginAttempts},
            last_failed_login_at = #{lastFailedLoginAt},
            account_locked = #{accountLocked},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{id} AND tenant_id = #{tenantId}
    """)
    int updateLoginTracking(User user);
    
    /**
     * Soft delete user (deactivate)
     */
    @Update("""
        UPDATE users SET 
            is_active = false,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{id} AND tenant_id = #{tenantId}
    """)
    int deactivateUser(String id, String tenantId);
    
    /**
     * Get user count for tenant
     */
    @Select("SELECT COUNT(*) FROM users WHERE tenant_id = #{tenantId} AND is_active = true")
    long getActiveUserCount(String tenantId);
    
    /**
     * Clean up expired invitation tokens
     */
    @Update("""
        UPDATE users SET 
            invitation_token = NULL,
            invitation_expires_at = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE invitation_expires_at < CURRENT_TIMESTAMP
          AND invitation_token IS NOT NULL
    """)
    int cleanupExpiredInvitations();
}
package io.factorialsystems.authorizationserver.mapper;

import io.factorialsystems.authorizationserver.model.UserRole;
import org.apache.ibatis.annotations.*;

import java.util.List;
import java.util.Optional;

/**
 * MyBatis mapper for user-role assignment operations.
 * Manages the many-to-many relationship between users and roles with audit trail.
 */
@Mapper
public interface UserRoleMapper {
    
    /**
     * Create a new user-role assignment
     */
    @Insert("""
        INSERT INTO user_roles (
            id, user_id, role_id, assigned_by, expires_at, is_active
        ) VALUES (
            #{id}, #{userId}, #{roleId}, #{assignedBy}, #{expiresAt}, #{isActive}
        )
    """)
    int insertUserRole(UserRole userRole);
    
    /**
     * Update a user-role assignment
     */
    @Update("""
        UPDATE user_roles SET 
            expires_at = #{expiresAt},
            is_active = #{isActive}
        WHERE id = #{id}
    """)
    int updateUserRole(UserRole userRole);
    
    /**
     * Find user-role assignment by ID
     */
    @Select("""
        SELECT id, user_id, role_id, assigned_at, assigned_by, expires_at, is_active
        FROM user_roles 
        WHERE id = #{id}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "roleId", column = "role_id"),
        @Result(property = "assignedAt", column = "assigned_at"),
        @Result(property = "assignedBy", column = "assigned_by"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "isActive", column = "is_active")
    })
    Optional<UserRole> findById(String id);
    
    /**
     * Find user-role assignment by user and role
     */
    @Select("""
        SELECT id, user_id, role_id, assigned_at, assigned_by, expires_at, is_active
        FROM user_roles 
        WHERE user_id = #{userId} AND role_id = #{roleId}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "roleId", column = "role_id"),
        @Result(property = "assignedAt", column = "assigned_at"),
        @Result(property = "assignedBy", column = "assigned_by"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "isActive", column = "is_active")
    })
    Optional<UserRole> findByUserAndRole(String userId, String roleId);
    
    /**
     * List all role assignments for a user
     */
    @Select("""
        SELECT id, user_id, role_id, assigned_at, assigned_by, expires_at, is_active
        FROM user_roles 
        WHERE user_id = #{userId}
        ORDER BY assigned_at DESC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "roleId", column = "role_id"),
        @Result(property = "assignedAt", column = "assigned_at"),
        @Result(property = "assignedBy", column = "assigned_by"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "isActive", column = "is_active")
    })
    List<UserRole> findByUserId(String userId);
    
    /**
     * List active role assignments for a user
     */
    @Select("""
        SELECT id, user_id, role_id, assigned_at, assigned_by, expires_at, is_active
        FROM user_roles 
        WHERE user_id = #{userId} 
          AND is_active = true
          AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        ORDER BY assigned_at DESC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "roleId", column = "role_id"),
        @Result(property = "assignedAt", column = "assigned_at"),
        @Result(property = "assignedBy", column = "assigned_by"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "isActive", column = "is_active")
    })
    List<UserRole> findActiveByUserId(String userId);
    
    /**
     * List all user assignments for a role
     */
    @Select("""
        SELECT id, user_id, role_id, assigned_at, assigned_by, expires_at, is_active
        FROM user_roles 
        WHERE role_id = #{roleId}
        ORDER BY assigned_at DESC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "roleId", column = "role_id"),
        @Result(property = "assignedAt", column = "assigned_at"),
        @Result(property = "assignedBy", column = "assigned_by"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "isActive", column = "is_active")
    })
    List<UserRole> findByRoleId(String roleId);
    
    /**
     * List active user assignments for a role
     */
    @Select("""
        SELECT id, user_id, role_id, assigned_at, assigned_by, expires_at, is_active
        FROM user_roles 
        WHERE role_id = #{roleId} 
          AND is_active = true
          AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
        ORDER BY assigned_at DESC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "roleId", column = "role_id"),
        @Result(property = "assignedAt", column = "assigned_at"),
        @Result(property = "assignedBy", column = "assigned_by"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "isActive", column = "is_active")
    })
    List<UserRole> findActiveByRoleId(String roleId);
    
    /**
     * List role assignments made by a specific user (for audit trail)
     */
    @Select("""
        SELECT id, user_id, role_id, assigned_at, assigned_by, expires_at, is_active
        FROM user_roles 
        WHERE assigned_by = #{assignedBy}
        ORDER BY assigned_at DESC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "roleId", column = "role_id"),
        @Result(property = "assignedAt", column = "assigned_at"),
        @Result(property = "assignedBy", column = "assigned_by"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "isActive", column = "is_active")
    })
    List<UserRole> findByAssignedBy(String assignedBy);
    
    /**
     * List expiring role assignments (for notifications)
     */
    @Select("""
        SELECT id, user_id, role_id, assigned_at, assigned_by, expires_at, is_active
        FROM user_roles 
        WHERE expires_at IS NOT NULL
          AND expires_at > CURRENT_TIMESTAMP 
          AND expires_at < CURRENT_TIMESTAMP + INTERVAL '#{days} days'
          AND is_active = true
        ORDER BY expires_at ASC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "roleId", column = "role_id"),
        @Result(property = "assignedAt", column = "assigned_at"),
        @Result(property = "assignedBy", column = "assigned_by"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "isActive", column = "is_active")
    })
    List<UserRole> findExpiringInDays(int days);
    
    /**
     * List expired role assignments
     */
    @Select("""
        SELECT id, user_id, role_id, assigned_at, assigned_by, expires_at, is_active
        FROM user_roles 
        WHERE expires_at IS NOT NULL
          AND expires_at < CURRENT_TIMESTAMP
          AND is_active = true
        ORDER BY expires_at DESC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "roleId", column = "role_id"),
        @Result(property = "assignedAt", column = "assigned_at"),
        @Result(property = "assignedBy", column = "assigned_by"),
        @Result(property = "expiresAt", column = "expires_at"),
        @Result(property = "isActive", column = "is_active")
    })
    List<UserRole> findExpiredAssignments();
    
    /**
     * Check if user has specific role assignment
     */
    @Select("""
        SELECT COUNT(*) FROM user_roles 
        WHERE user_id = #{userId} 
          AND role_id = #{roleId}
          AND is_active = true
          AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    """)
    boolean userHasRole(String userId, String roleId);
    
    /**
     * Check if user has active role assignments
     */
    @Select("""
        SELECT COUNT(*) FROM user_roles 
        WHERE user_id = #{userId}
          AND is_active = true
          AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    """)
    boolean userHasActiveRoles(String userId);
    
    /**
     * Deactivate role assignment
     */
    @Update("""
        UPDATE user_roles SET 
            is_active = false
        WHERE id = #{id}
    """)
    int deactivateUserRole(String id);
    
    /**
     * Deactivate role assignment by user and role
     */
    @Update("""
        UPDATE user_roles SET 
            is_active = false
        WHERE user_id = #{userId} AND role_id = #{roleId}
    """)
    int deactivateUserRoleByUserAndRole(String userId, String roleId);
    
    /**
     * Extend role assignment expiration
     */
    @Update("""
        UPDATE user_roles SET 
            expires_at = #{newExpiresAt}
        WHERE id = #{id}
    """)
    int extendRoleAssignment(String id, java.time.LocalDateTime newExpiresAt);
    
    /**
     * Make role assignment permanent (remove expiration)
     */
    @Update("""
        UPDATE user_roles SET 
            expires_at = NULL
        WHERE id = #{id}
    """)
    int makePermanent(String id);
    
    /**
     * Clean up expired role assignments (deactivate them)
     */
    @Update("""
        UPDATE user_roles SET 
            is_active = false
        WHERE expires_at IS NOT NULL 
          AND expires_at < CURRENT_TIMESTAMP
          AND is_active = true
    """)
    int deactivateExpiredAssignments();
    
    /**
     * Get role assignment statistics for a tenant (join with users table)
     */
    @Select("""
        SELECT COUNT(*) as total_assignments
        FROM user_roles ur
        INNER JOIN users u ON ur.user_id = u.id
        WHERE u.tenant_id = #{tenantId}
          AND ur.is_active = true
          AND (ur.expires_at IS NULL OR ur.expires_at > CURRENT_TIMESTAMP)
    """)
    long getActiveAssignmentCountByTenant(String tenantId);
    
    /**
     * Get role assignment count for a specific role
     */
    @Select("""
        SELECT COUNT(*) FROM user_roles 
        WHERE role_id = #{roleId}
          AND is_active = true
          AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    """)
    long getActiveAssignmentCountByRole(String roleId);
    
    /**
     * List users with a specific role (for role management)
     */
    @Select("""
        SELECT u.id, u.tenant_id, u.username, u.email, u.first_name, u.last_name,
               u.is_active, u.is_tenant_admin, u.created_at
        FROM users u
        INNER JOIN user_roles ur ON u.id = ur.user_id
        WHERE ur.role_id = #{roleId}
          AND ur.is_active = true
          AND (ur.expires_at IS NULL OR ur.expires_at > CURRENT_TIMESTAMP)
          AND u.is_active = true
        ORDER BY u.username
    """)
    List<io.factorialsystems.authorizationserver.model.User> findUsersByRoleId(String roleId);
    
    /**
     * Bulk assign role to multiple users
     */
    @Insert({
        "<script>",
        "INSERT INTO user_roles (id, user_id, role_id, assigned_by, is_active) VALUES",
        "<foreach collection='userRoles' item='userRole' separator=','>",
        "(#{userRole.id}, #{userRole.userId}, #{userRole.roleId}, #{userRole.assignedBy}, #{userRole.isActive})",
        "</foreach>",
        "</script>"
    })
    int bulkInsertUserRoles(@Param("userRoles") List<UserRole> userRoles);
    
    /**
     * Bulk deactivate role assignments for multiple users
     */
    @Update({
        "<script>",
        "UPDATE user_roles SET is_active = false WHERE user_id IN",
        "<foreach collection='userIds' item='userId' open='(' separator=',' close=')'>",
        "#{userId}",
        "</foreach>",
        "AND role_id = #{roleId}",
        "</script>"
    })
    int bulkDeactivateByUsersAndRole(@Param("userIds") List<String> userIds, @Param("roleId") String roleId);
}
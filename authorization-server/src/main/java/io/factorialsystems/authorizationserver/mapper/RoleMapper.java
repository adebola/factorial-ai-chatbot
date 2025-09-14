package io.factorialsystems.authorizationserver.mapper;

import io.factorialsystems.authorizationserver.model.Role;
import org.apache.ibatis.annotations.*;

import java.util.List;
import java.util.Optional;

/**
 * MyBatis mapper for role CRUD operations.
 * Simplified for global roles only - all roles are shared across tenants.
 */
@Mapper
public interface RoleMapper {
    
    /**
     * Create a new role
     */
    @Insert("""
        INSERT INTO roles (
            id, name, description, permissions, is_active, created_at, updated_at
        ) VALUES (
            #{id}, #{name}, #{description}, 
            #{permissions, typeHandler=io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler},
            #{isActive}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        )
    """)
    int insertRole(Role role);
    
    /**
     * Update an existing role
     */
    @Update("""
        UPDATE roles SET 
            name = #{name},
            description = #{description},
            permissions = #{permissions, typeHandler=io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler},
            is_active = #{isActive},
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{id}
    """)
    int updateRole(Role role);
    
    /**
     * Find role by ID
     */
    @Select("""
        SELECT id, name, description, permissions, is_active, created_at, updated_at
        FROM roles 
        WHERE id = #{id}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "description", column = "description"),
        @Result(property = "permissions", column = "permissions", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Optional<Role> findById(String id);
    
    /**
     * Find role by name
     */
    @Select("""
        SELECT id, name, description, permissions, is_active, created_at, updated_at
        FROM roles 
        WHERE name = #{name} AND is_active = true
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "description", column = "description"),
        @Result(property = "permissions", column = "permissions", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Optional<Role> findByName(String name);
    
    /**
     * List all active roles
     */
    @Select("""
        SELECT id, name, description, permissions, is_active, created_at, updated_at
        FROM roles 
        WHERE is_active = true
        ORDER BY name
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "description", column = "description"),
        @Result(property = "permissions", column = "permissions", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<Role> findAllActiveRoles();
    
    /**
     * List all roles (including inactive)
     */
    @Select("""
        SELECT id, name, description, permissions, is_active, created_at, updated_at
        FROM roles 
        ORDER BY is_active DESC, name ASC
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "description", column = "description"),
        @Result(property = "permissions", column = "permissions", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<Role> findAllRoles();
    
    /**
     * Find roles for a user (via user_roles table)
     */
    @Select("""
        SELECT r.id, r.name, r.description, r.permissions, r.is_active, r.created_at, r.updated_at
        FROM roles r
        INNER JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = #{userId} 
          AND ur.is_active = true 
          AND r.is_active = true
          AND (ur.expires_at IS NULL OR ur.expires_at > CURRENT_TIMESTAMP)
        ORDER BY r.name
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "description", column = "description"),
        @Result(property = "permissions", column = "permissions", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<Role> findByUserId(String userId);
    
    /**
     * Check if role name exists
     */
    @Select("SELECT COUNT(*) FROM roles WHERE name = #{name}")
    boolean existsByName(String name);
    
    /**
     * Deactivate role
     */
    @Update("""
        UPDATE roles SET 
            is_active = false,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{id}
    """)
    int deactivateRole(String id);
    
    /**
     * Activate role
     */
    @Update("""
        UPDATE roles SET 
            is_active = true,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = #{id}
    """)
    int activateRole(String id);
    
    /**
     * Get total role count
     */
    @Select("SELECT COUNT(*) FROM roles WHERE is_active = true")
    long getActiveRoleCount();
    
    /**
     * Find roles with specific permission
     */
    @Select("""
        SELECT id, name, description, permissions, is_active, created_at, updated_at
        FROM roles 
        WHERE permissions @> to_jsonb(ARRAY[#{permission}])
          AND is_active = true
        ORDER BY name
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "description", column = "description"),
        @Result(property = "permissions", column = "permissions", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<Role> findByPermission(String permission);
    
    /**
     * Find roles containing any of the specified permissions
     */
    @Select("""
        SELECT DISTINCT r.id, r.name, r.description, r.permissions, r.is_active, r.created_at, r.updated_at
        FROM roles r, jsonb_array_elements_text(r.permissions) AS perm
        WHERE perm = ANY(#{permissions})
          AND r.is_active = true
        ORDER BY r.name
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "description", column = "description"),
        @Result(property = "permissions", column = "permissions", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<Role> findByPermissions(@Param("permissions") String[] permissions);
    
    /**
     * Search roles by name or description
     */
    @Select("""
        SELECT id, name, description, permissions, is_active, created_at, updated_at
        FROM roles 
        WHERE (LOWER(name) LIKE LOWER(CONCAT('%', #{searchTerm}, '%'))
            OR LOWER(description) LIKE LOWER(CONCAT('%', #{searchTerm}, '%')))
          AND is_active = true
        ORDER BY name
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "description", column = "description"),
        @Result(property = "permissions", column = "permissions", 
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonbStringListTypeHandler.class),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<Role> searchRoles(String searchTerm);
}
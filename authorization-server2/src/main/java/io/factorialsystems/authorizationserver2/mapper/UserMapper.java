package io.factorialsystems.authorizationserver2.mapper;

import io.factorialsystems.authorizationserver2.model.Role;
import io.factorialsystems.authorizationserver2.model.User;
import org.apache.ibatis.annotations.*;

import java.util.List;

@Mapper
public interface UserMapper {
    
    @Select("SELECT u.*, t.name as tenant_name, t.domain as tenant_domain, t.api_key " +
            "FROM users u " +
            "LEFT JOIN tenants t ON u.tenant_id = t.id " +
            "WHERE u.username = #{username} AND u.is_active = true")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "password", column = "password"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isEmailVerified", column = "is_email_verified"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "roles", column = "id", javaType = List.class, 
                many = @Many(select = "findRolesByUserId"))
    })
    User findByUsername(@Param("username") String username);
    
    @Select("SELECT u.*, t.name as tenant_name, t.domain as tenant_domain, t.api_key " +
            "FROM users u " +
            "LEFT JOIN tenants t ON u.tenant_id = t.id " +
            "WHERE u.email = #{email} AND u.is_active = true")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "password", column = "password"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isEmailVerified", column = "is_email_verified"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "roles", column = "id", javaType = List.class, 
                many = @Many(select = "findRolesByUserId"))
    })
    User findByEmail(@Param("email") String email);
    
    @Select("SELECT r.* FROM roles r " +
            "JOIN user_roles ur ON r.id = ur.role_id " +
            "WHERE ur.user_id = #{userId} AND r.is_active = true")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "description", column = "description"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<Role> findRolesByUserId(@Param("userId") String userId);
    
    @Select("SELECT * FROM users WHERE id = #{id}")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "password", column = "password"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isEmailVerified", column = "is_email_verified"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    User findById(@Param("id") String id);
    
    @Update("UPDATE users SET last_login_at = #{lastLoginAt}, updated_at = #{updatedAt} WHERE id = #{id}")
    int updateLastLogin(User user);
    
    @Insert("INSERT INTO users (id, tenant_id, username, email, password, first_name, last_name, " +
            "is_active, is_email_verified, created_at, updated_at) " +
            "VALUES (#{id}, #{tenantId}, #{username}, #{email}, #{password}, #{firstName}, #{lastName}, " +
            "#{isActive}, #{isEmailVerified}, #{createdAt}, #{updatedAt})")
    int insert(User user);
    
    @Update("UPDATE users SET username = #{username}, email = #{email}, password = #{password}, " +
            "first_name = #{firstName}, last_name = #{lastName}, is_active = #{isActive}, " +
            "is_email_verified = #{isEmailVerified}, updated_at = #{updatedAt} WHERE id = #{id}")
    int update(User user);
    
    @Insert("INSERT INTO user_roles (user_id, role_id) VALUES (#{userId}, #{roleId})")
    int insertUserRole(@Param("userId") String userId, @Param("roleId") String roleId);
    
    @Select("SELECT id FROM roles WHERE name = #{roleName} AND is_active = true")
    String findRoleIdByName(@Param("roleName") String roleName);
    
    @Select("SELECT * FROM users WHERE tenant_id = #{tenantId} AND is_active = true")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "username", column = "username"),
        @Result(property = "email", column = "email"),
        @Result(property = "password", column = "password"),
        @Result(property = "firstName", column = "first_name"),
        @Result(property = "lastName", column = "last_name"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "isEmailVerified", column = "is_email_verified"),
        @Result(property = "lastLoginAt", column = "last_login_at"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    List<User> findByTenantId(@Param("tenantId") String tenantId);
}
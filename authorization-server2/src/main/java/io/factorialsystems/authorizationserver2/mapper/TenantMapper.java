package io.factorialsystems.authorizationserver2.mapper;

import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.typehandler.JsonTypeHandler;
import org.apache.ibatis.annotations.*;

@Mapper
public interface TenantMapper {
    
    @Select("SELECT * FROM tenants WHERE id = #{id}")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "config", column = "config", typeHandler = io.factorialsystems.authorizationserver2.typehandler.JsonTypeHandler.class),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "subscriptionId", column = "subscription_id"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Tenant findById(@Param("id") String id);

    @Select("SELECT * FROM tenants WHERE domain = #{domain}")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "config", column = "config", typeHandler = io.factorialsystems.authorizationserver2.typehandler.JsonTypeHandler.class),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "subscriptionId", column = "subscription_id"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Tenant findByDomain(@Param("domain") String domain);
    
    @Select("SELECT * FROM tenants WHERE name = #{name}")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "config", column = "config", typeHandler = io.factorialsystems.authorizationserver2.typehandler.JsonTypeHandler.class),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "subscriptionId", column = "subscription_id"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Tenant findByName(@Param("name") String name);
    
    @Select("SELECT * FROM tenants WHERE api_key = #{apiKey}")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "config", column = "config", typeHandler = io.factorialsystems.authorizationserver2.typehandler.JsonTypeHandler.class),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "subscriptionId", column = "subscription_id"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    Tenant findByApiKey(@Param("apiKey") String apiKey);
    
    @Insert("INSERT INTO tenants (id, name, domain, api_key, config, plan_id, subscription_id, is_active, created_at, updated_at) " +
            "VALUES (#{id}, #{name}, #{domain}, #{apiKey}, #{config,typeHandler=io.factorialsystems.authorizationserver2.typehandler.JsonTypeHandler}, #{planId}, #{subscriptionId}, #{isActive}, #{createdAt}, #{updatedAt})")
    int insert(Tenant tenant);

    @Update("UPDATE tenants SET name = #{name}, domain = #{domain}, " +
            "api_key = #{apiKey}, config = #{config,typeHandler=io.factorialsystems.authorizationserver2.typehandler.JsonTypeHandler}, plan_id = #{planId}, subscription_id = #{subscriptionId}, " +
            "is_active = #{isActive}, updated_at = #{updatedAt} WHERE id = #{id}")
    int update(Tenant tenant);
    
    @Delete("DELETE FROM tenants WHERE id = #{id}")
    int deleteById(@Param("id") String id);
    
    @Update("UPDATE tenants SET plan_id = #{planId}, updated_at = CURRENT_TIMESTAMP WHERE id = #{id}")
    int updatePlanId(@Param("id") String tenantId, @Param("planId") String planId);

    @Update("UPDATE tenants SET subscription_id = #{subscriptionId}, plan_id = #{planId}, updated_at = CURRENT_TIMESTAMP WHERE id = #{id}")
    int updateSubscriptionAndPlan(@Param("id") String tenantId,
                                   @Param("subscriptionId") String subscriptionId,
                                   @Param("planId") String planId);

    @Select("SELECT * FROM tenants ORDER BY created_at DESC")
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "name", column = "name"),
        @Result(property = "domain", column = "domain"),
        @Result(property = "apiKey", column = "api_key"),
        @Result(property = "config", column = "config", typeHandler = io.factorialsystems.authorizationserver2.typehandler.JsonTypeHandler.class),
        @Result(property = "planId", column = "plan_id"),
        @Result(property = "subscriptionId", column = "subscription_id"),
        @Result(property = "isActive", column = "is_active"),
        @Result(property = "createdAt", column = "created_at"),
        @Result(property = "updatedAt", column = "updated_at")
    })
    java.util.List<Tenant> findAll();
}
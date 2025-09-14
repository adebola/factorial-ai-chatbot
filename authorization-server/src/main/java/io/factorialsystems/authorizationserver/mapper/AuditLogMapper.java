package io.factorialsystems.authorizationserver.mapper;

import io.factorialsystems.authorizationserver.model.AuditLog;
import org.apache.ibatis.annotations.*;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

/**
 * MyBatis mapper for audit log operations.
 * Tracks security and operational events for compliance and monitoring.
 */
@Mapper
public interface AuditLogMapper {
    
    /**
     * Create a new audit log entry
     */
    @Insert("""
        INSERT INTO audit_logs (
            id, tenant_id, user_id, event_type, event_description, 
            ip_address, user_agent, additional_data
        ) VALUES (
            #{id}, #{tenantId}, #{userId}, #{eventType}, #{eventDescription},
            #{ipAddress}, #{userAgent}, #{additionalData,typeHandler=io.factorialsystems.authorizationserver.typehandler.JsonTypeHandler}
        )
    """)
    int insertAuditLog(AuditLog auditLog);
    
    /**
     * Find audit log by ID
     */
    @Select("""
        SELECT id, tenant_id, user_id, event_type, event_description,
               ip_address, user_agent, additional_data, created_at
        FROM audit_logs 
        WHERE id = #{id}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "eventType", column = "event_type"),
        @Result(property = "eventDescription", column = "event_description"),
        @Result(property = "ipAddress", column = "ip_address"),
        @Result(property = "userAgent", column = "user_agent"),
        @Result(property = "additionalData", column = "additional_data",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonTypeHandler.class),
        @Result(property = "createdAt", column = "created_at")
    })
    Optional<AuditLog> findById(String id);
    
    /**
     * List audit logs for a tenant (with pagination support)
     */
    @Select("""
        SELECT id, tenant_id, user_id, event_type, event_description,
               ip_address, user_agent, additional_data, created_at
        FROM audit_logs 
        WHERE tenant_id = #{tenantId}
        ORDER BY created_at DESC
        LIMIT #{limit} OFFSET #{offset}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "eventType", column = "event_type"),
        @Result(property = "eventDescription", column = "event_description"),
        @Result(property = "ipAddress", column = "ip_address"),
        @Result(property = "userAgent", column = "user_agent"),
        @Result(property = "additionalData", column = "additional_data",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonTypeHandler.class),
        @Result(property = "createdAt", column = "created_at")
    })
    List<AuditLog> findByTenant(String tenantId, int limit, int offset);
    
    /**
     * List audit logs for a user (with pagination support)
     */
    @Select("""
        SELECT id, tenant_id, user_id, event_type, event_description,
               ip_address, user_agent, additional_data, created_at
        FROM audit_logs 
        WHERE user_id = #{userId}
        ORDER BY created_at DESC
        LIMIT #{limit} OFFSET #{offset}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "eventType", column = "event_type"),
        @Result(property = "eventDescription", column = "event_description"),
        @Result(property = "ipAddress", column = "ip_address"),
        @Result(property = "userAgent", column = "user_agent"),
        @Result(property = "additionalData", column = "additional_data",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonTypeHandler.class),
        @Result(property = "createdAt", column = "created_at")
    })
    List<AuditLog> findByUser(String userId, int limit, int offset);
    
    /**
     * List audit logs by event type
     */
    @Select("""
        SELECT id, tenant_id, user_id, event_type, event_description,
               ip_address, user_agent, additional_data, created_at
        FROM audit_logs 
        WHERE event_type = #{eventType}
          AND (#{tenantId} IS NULL OR tenant_id = #{tenantId})
        ORDER BY created_at DESC
        LIMIT #{limit} OFFSET #{offset}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "eventType", column = "event_type"),
        @Result(property = "eventDescription", column = "event_description"),
        @Result(property = "ipAddress", column = "ip_address"),
        @Result(property = "userAgent", column = "user_agent"),
        @Result(property = "additionalData", column = "additional_data",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonTypeHandler.class),
        @Result(property = "createdAt", column = "created_at")
    })
    List<AuditLog> findByEventType(String eventType, String tenantId, int limit, int offset);
    
    /**
     * List security events (login failures, permission denials, etc.)
     */
    @Select("""
        SELECT id, tenant_id, user_id, event_type, event_description,
               ip_address, user_agent, additional_data, created_at
        FROM audit_logs 
        WHERE event_type IN ('LOGIN_FAILED', 'ACCOUNT_LOCKED', 'PERMISSION_DENIED', 
                            'INVALID_TOKEN', 'SUSPICIOUS_ACTIVITY')
          AND (#{tenantId} IS NULL OR tenant_id = #{tenantId})
          AND created_at >= #{fromDate}
          AND created_at <= #{toDate}
        ORDER BY created_at DESC
        LIMIT #{limit} OFFSET #{offset}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "eventType", column = "event_type"),
        @Result(property = "eventDescription", column = "event_description"),
        @Result(property = "ipAddress", column = "ip_address"),
        @Result(property = "userAgent", column = "user_agent"),
        @Result(property = "additionalData", column = "additional_data",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonTypeHandler.class),
        @Result(property = "createdAt", column = "created_at")
    })
    List<AuditLog> findSecurityEvents(String tenantId, LocalDateTime fromDate, 
                                     LocalDateTime toDate, int limit, int offset);
    
    /**
     * List audit logs by IP address (for security analysis)
     */
    @Select("""
        SELECT id, tenant_id, user_id, event_type, event_description,
               ip_address, user_agent, additional_data, created_at
        FROM audit_logs 
        WHERE ip_address = #{ipAddress}
          AND created_at >= #{fromDate}
        ORDER BY created_at DESC
        LIMIT #{limit} OFFSET #{offset}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "eventType", column = "event_type"),
        @Result(property = "eventDescription", column = "event_description"),
        @Result(property = "ipAddress", column = "ip_address"),
        @Result(property = "userAgent", column = "user_agent"),
        @Result(property = "additionalData", column = "additional_data",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonTypeHandler.class),
        @Result(property = "createdAt", column = "created_at")
    })
    List<AuditLog> findByIpAddress(String ipAddress, LocalDateTime fromDate, int limit, int offset);
    
    /**
     * List recent audit logs (general monitoring)
     */
    @Select("""
        SELECT id, tenant_id, user_id, event_type, event_description,
               ip_address, user_agent, additional_data, created_at
        FROM audit_logs 
        WHERE created_at >= #{fromDate}
          AND (#{tenantId} IS NULL OR tenant_id = #{tenantId})
        ORDER BY created_at DESC
        LIMIT #{limit} OFFSET #{offset}
    """)
    @Results({
        @Result(property = "id", column = "id"),
        @Result(property = "tenantId", column = "tenant_id"),
        @Result(property = "userId", column = "user_id"),
        @Result(property = "eventType", column = "event_type"),
        @Result(property = "eventDescription", column = "event_description"),
        @Result(property = "ipAddress", column = "ip_address"),
        @Result(property = "userAgent", column = "user_agent"),
        @Result(property = "additionalData", column = "additional_data",
                typeHandler = io.factorialsystems.authorizationserver.typehandler.JsonTypeHandler.class),
        @Result(property = "createdAt", column = "created_at")
    })
    List<AuditLog> findRecent(LocalDateTime fromDate, String tenantId, int limit, int offset);
    
    /**
     * Count audit logs by tenant
     */
    @Select("SELECT COUNT(*) FROM audit_logs WHERE tenant_id = #{tenantId}")
    long countByTenant(String tenantId);
    
    /**
     * Count audit logs by user
     */
    @Select("SELECT COUNT(*) FROM audit_logs WHERE user_id = #{userId}")
    long countByUser(String userId);
    
    /**
     * Count security events in time range
     */
    @Select("""
        SELECT COUNT(*) FROM audit_logs 
        WHERE event_type IN ('LOGIN_FAILED', 'ACCOUNT_LOCKED', 'PERMISSION_DENIED', 
                            'INVALID_TOKEN', 'SUSPICIOUS_ACTIVITY')
          AND (#{tenantId} IS NULL OR tenant_id = #{tenantId})
          AND created_at >= #{fromDate}
          AND created_at <= #{toDate}
    """)
    long countSecurityEvents(String tenantId, LocalDateTime fromDate, LocalDateTime toDate);
    
    /**
     * Get event type statistics
     */
    @Select("""
        SELECT event_type, COUNT(*) as event_count
        FROM audit_logs 
        WHERE (#{tenantId} IS NULL OR tenant_id = #{tenantId})
          AND created_at >= #{fromDate}
          AND created_at <= #{toDate}
        GROUP BY event_type
        ORDER BY event_count DESC
    """)
    List<java.util.Map<String, Object>> getEventTypeStatistics(String tenantId, 
                                                              LocalDateTime fromDate, 
                                                              LocalDateTime toDate);
    
    /**
     * Get top IP addresses by activity
     */
    @Select("""
        SELECT ip_address, COUNT(*) as activity_count
        FROM audit_logs 
        WHERE ip_address IS NOT NULL
          AND (#{tenantId} IS NULL OR tenant_id = #{tenantId})
          AND created_at >= #{fromDate}
          AND created_at <= #{toDate}
        GROUP BY ip_address
        ORDER BY activity_count DESC
        LIMIT #{limit}
    """)
    List<java.util.Map<String, Object>> getTopIpAddresses(String tenantId, 
                                                         LocalDateTime fromDate, 
                                                         LocalDateTime toDate, 
                                                         int limit);
    
    /**
     * Get user activity statistics
     */
    @Select("""
        SELECT u.username, u.email, COUNT(*) as activity_count,
               MAX(al.created_at) as last_activity
        FROM audit_logs al
        INNER JOIN users u ON al.user_id = u.id
        WHERE (#{tenantId} IS NULL OR al.tenant_id = #{tenantId})
          AND al.created_at >= #{fromDate}
          AND al.created_at <= #{toDate}
        GROUP BY u.id, u.username, u.email
        ORDER BY activity_count DESC
        LIMIT #{limit}
    """)
    List<java.util.Map<String, Object>> getUserActivityStatistics(String tenantId, 
                                                                 LocalDateTime fromDate, 
                                                                 LocalDateTime toDate, 
                                                                 int limit);
    
    /**
     * Clean up old audit logs (for data retention)
     */
    @Delete("""
        DELETE FROM audit_logs 
        WHERE created_at < #{cutoffDate}
    """)
    int deleteOldLogs(LocalDateTime cutoffDate);
    
    /**
     * Clean up old audit logs for specific tenant
     */
    @Delete("""
        DELETE FROM audit_logs 
        WHERE tenant_id = #{tenantId} 
          AND created_at < #{cutoffDate}
    """)
    int deleteOldLogsByTenant(String tenantId, LocalDateTime cutoffDate);
    
    /**
     * Archive old audit logs to another table (for compliance)
     */
    @Insert("""
        INSERT INTO audit_logs_archive 
        SELECT * FROM audit_logs 
        WHERE created_at < #{cutoffDate}
    """)
    int archiveOldLogs(LocalDateTime cutoffDate);
    
    /**
     * Get audit log retention statistics
     */
    @Select("""
        SELECT 
            COUNT(*) as total_logs,
            COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as last_7_days,
            COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '30 days' THEN 1 END) as last_30_days,
            COUNT(CASE WHEN created_at >= CURRENT_DATE - INTERVAL '90 days' THEN 1 END) as last_90_days,
            MIN(created_at) as oldest_log,
            MAX(created_at) as newest_log
        FROM audit_logs
        WHERE (#{tenantId} IS NULL OR tenant_id = #{tenantId})
    """)
    java.util.Map<String, Object> getRetentionStatistics(String tenantId);
}
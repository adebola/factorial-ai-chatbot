package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.mapper.TenantMapper;
import io.factorialsystems.authorizationserver2.mapper.UserMapper;
import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.service.BillingServiceClient;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.*;

import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.*;
import java.util.stream.Collectors;

/**
 * Super Admin controller for system-wide analytics
 * All endpoints require ROLE_SYSTEM_ADMIN authority
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/admin/analytics")
@RequiredArgsConstructor
public class SystemAnalyticsController {

    private final TenantMapper tenantMapper;
    private final UserMapper userMapper;
    private final BillingServiceClient billingServiceClient;

    /**
     * Get platform-wide metrics
     * GET /api/v1/admin/analytics/platform-metrics
     */
    @GetMapping("/platform-metrics")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> getPlatformMetrics(
            @RequestHeader("Authorization") String authorizationHeader) {
        log.info("System admin requesting platform metrics");

        // Get all tenants and users
        List<Tenant> allTenants = tenantMapper.findAll();
        List<User> allUsers = userMapper.findAllUsers();

        // Calculate tenant stats
        long totalTenants = allTenants.size();
        long activeTenants = allTenants.stream().filter(Tenant::getIsActive).count();
        long inactiveTenants = totalTenants - activeTenants;

        // Calculate user stats
        long totalUsers = allUsers.size();
        long activeUsers = allUsers.stream().filter(User::getIsActive).count();
        long verifiedUsers = allUsers.stream().filter(User::getIsEmailVerified).count();

        // Calculate growth metrics (last 30 days)
        OffsetDateTime thirtyDaysAgo = OffsetDateTime.now().minusDays(30);
        long newTenantsLast30Days = allTenants.stream()
            .filter(t -> t.getCreatedAt().isAfter(thirtyDaysAgo))
            .count();
        long newUsersLast30Days = allUsers.stream()
            .filter(u -> u.getCreatedAt().isAfter(thirtyDaysAgo))
            .count();

        // Try to get billing metrics
        Map<String, Object> billingMetrics = new HashMap<>();
        try {
            billingMetrics = billingServiceClient.getPlatformMetrics(authorizationHeader);
        } catch (Exception e) {
            log.warn("Failed to fetch billing metrics: {}", e.getMessage());
            billingMetrics.put("error", "Billing metrics unavailable");
        }

        // Build response
        Map<String, Object> response = new HashMap<>();
        response.put("tenants", Map.of(
            "total", totalTenants,
            "active", activeTenants,
            "inactive", inactiveTenants,
            "newLast30Days", newTenantsLast30Days
        ));
        response.put("users", Map.of(
            "total", totalUsers,
            "active", activeUsers,
            "verified", verifiedUsers,
            "newLast30Days", newUsersLast30Days
        ));
        response.put("billing", billingMetrics);
        response.put("timestamp", OffsetDateTime.now());

        log.info("Platform metrics: {} tenants ({} active), {} users ({} active)",
                totalTenants, activeTenants, totalUsers, activeUsers);
        return ResponseEntity.ok(response);
    }

    /**
     * Get tenant growth over time
     * GET /api/v1/admin/analytics/tenant-growth?days=90
     */
    @GetMapping("/tenant-growth")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> getTenantGrowth(
            @RequestParam(defaultValue = "90") int days) {

        log.info("System admin requesting tenant growth for {} days", days);

        List<Tenant> allTenants = tenantMapper.findAll();

        // Group tenants by creation date
        Map<LocalDate, Long> tenantsByDate = allTenants.stream()
            .filter(t -> t.getCreatedAt().isAfter(OffsetDateTime.now().minusDays(days)))
            .collect(Collectors.groupingBy(
                t -> t.getCreatedAt().toLocalDate(),
                Collectors.counting()
            ));

        // Build time series data
        List<Map<String, Object>> timeSeries = new ArrayList<>();
        LocalDate startDate = LocalDate.now().minusDays(days);
        long cumulativeCount = allTenants.stream()
            .filter(t -> t.getCreatedAt().isBefore(startDate.atStartOfDay().atOffset(OffsetDateTime.now().getOffset())))
            .count();

        for (int i = 0; i <= days; i++) {
            LocalDate date = startDate.plusDays(i);
            long newTenants = tenantsByDate.getOrDefault(date, 0L);
            cumulativeCount += newTenants;

            Map<String, Object> dataPoint = new HashMap<>();
            dataPoint.put("date", date.toString());
            dataPoint.put("newTenants", newTenants);
            dataPoint.put("totalTenants", cumulativeCount);
            timeSeries.add(dataPoint);
        }

        Map<String, Object> response = new HashMap<>();
        response.put("days", days);
        response.put("data", timeSeries);
        response.put("summary", Map.of(
            "totalTenants", allTenants.size(),
            "newInPeriod", tenantsByDate.values().stream().mapToLong(Long::longValue).sum()
        ));

        return ResponseEntity.ok(response);
    }

    /**
     * Get revenue analytics
     * GET /api/v1/admin/analytics/revenue
     */
    @GetMapping("/revenue")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> getRevenueAnalytics(
            @RequestHeader("Authorization") String authorizationHeader) {
        log.info("System admin requesting revenue analytics");

        try {
            Map<String, Object> revenueData = billingServiceClient.getRevenueAnalytics(authorizationHeader);
            return ResponseEntity.ok(revenueData);
        } catch (Exception e) {
            log.error("Failed to fetch revenue analytics: {}", e.getMessage());
            Map<String, Object> errorResponse = new HashMap<>();
            errorResponse.put("error", "Failed to fetch revenue analytics");
            errorResponse.put("message", e.getMessage());
            return ResponseEntity.status(500).body(errorResponse);
        }
    }

    /**
     * Get user growth over time
     * GET /api/v1/admin/analytics/user-growth?days=90
     */
    @GetMapping("/user-growth")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> getUserGrowth(
            @RequestParam(defaultValue = "90") int days) {

        log.info("System admin requesting user growth for {} days", days);

        List<User> allUsers = userMapper.findAllUsers();

        // Group users by creation date
        Map<LocalDate, Long> usersByDate = allUsers.stream()
            .filter(u -> u.getCreatedAt().isAfter(OffsetDateTime.now().minusDays(days)))
            .collect(Collectors.groupingBy(
                u -> u.getCreatedAt().toLocalDate(),
                Collectors.counting()
            ));

        // Build time series data
        List<Map<String, Object>> timeSeries = new ArrayList<>();
        LocalDate startDate = LocalDate.now().minusDays(days);
        long cumulativeCount = allUsers.stream()
            .filter(u -> u.getCreatedAt().isBefore(startDate.atStartOfDay().atOffset(OffsetDateTime.now().getOffset())))
            .count();

        for (int i = 0; i <= days; i++) {
            LocalDate date = startDate.plusDays(i);
            long newUsers = usersByDate.getOrDefault(date, 0L);
            cumulativeCount += newUsers;

            Map<String, Object> dataPoint = new HashMap<>();
            dataPoint.put("date", date.toString());
            dataPoint.put("newUsers", newUsers);
            dataPoint.put("totalUsers", cumulativeCount);
            timeSeries.add(dataPoint);
        }

        Map<String, Object> response = new HashMap<>();
        response.put("days", days);
        response.put("data", timeSeries);
        response.put("summary", Map.of(
            "totalUsers", allUsers.size(),
            "newInPeriod", usersByDate.values().stream().mapToLong(Long::longValue).sum()
        ));

        return ResponseEntity.ok(response);
    }

    /**
     * Get system health status
     * GET /api/v1/admin/analytics/health
     */
    @GetMapping("/health")
    @PreAuthorize("hasAuthority('ROLE_SYSTEM_ADMIN')")
    public ResponseEntity<Map<String, Object>> getSystemHealth(
            @RequestHeader("Authorization") String authorizationHeader) {
        log.info("System admin requesting system health");

        Map<String, Object> health = new HashMap<>();
        health.put("authorizationServer", "healthy");
        health.put("timestamp", OffsetDateTime.now());

        // Check billing service health
        try {
            billingServiceClient.getPlatformMetrics(authorizationHeader);
            health.put("billingService", "healthy");
        } catch (Exception e) {
            health.put("billingService", "unavailable");
            health.put("billingServiceError", e.getMessage());
        }

        return ResponseEntity.ok(health);
    }
}

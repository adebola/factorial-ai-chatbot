package io.factorialsystems.authorizationserver2.security;

import io.factorialsystems.authorizationserver2.service.AuditEventPublisher;
import io.factorialsystems.authorizationserver2.service.DatabaseUserDetailsService.CustomUserPrincipal;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.SavedRequestAwareAuthenticationSuccessHandler;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.util.HashMap;
import java.util.Map;

/**
 * Custom authentication success handler that publishes login.success audit events.
 * Extends SavedRequestAwareAuthenticationSuccessHandler to preserve the default
 * redirect behavior (redirecting to the originally requested URL after login).
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class CustomAuthenticationSuccessHandler extends SavedRequestAwareAuthenticationSuccessHandler {

    private final AuditEventPublisher auditEventPublisher;

    @Override
    public void onAuthenticationSuccess(HttpServletRequest request, HttpServletResponse response,
                                        Authentication authentication) throws IOException, ServletException {

        String tenantId = null;
        String userId = null;
        String email = null;
        String fullName = null;

        // Extract user details from the authentication principal
        if (authentication.getPrincipal() instanceof CustomUserPrincipal principal) {
            var user = principal.user();
            tenantId = user.getTenantId();
            userId = user.getId();
            email = user.getEmail();
            fullName = (user.getFirstName() != null ? user.getFirstName() : "")
                    + (user.getLastName() != null ? " " + user.getLastName() : "");
            fullName = fullName.trim();
        }

        log.info("Login successful for user: {} (tenant: {})", email, tenantId);

        // Publish audit event
        Map<String, Object> metadata = new HashMap<>();
        metadata.put("ip_address", getClientIp(request));
        metadata.put("user_agent", request.getHeader("User-Agent"));

        auditEventPublisher.publishSecurityEvent(
                "login.success",
                tenantId,
                userId,
                email,
                "user",
                "user",
                userId,
                null,
                Map.of("full_name", fullName != null ? fullName : "", "login_method", "form"),
                metadata
        );

        // Continue with default redirect behavior
        super.onAuthenticationSuccess(request, response, authentication);
    }

    private String getClientIp(HttpServletRequest request) {
        String xForwardedFor = request.getHeader("X-Forwarded-For");
        if (xForwardedFor != null && !xForwardedFor.isEmpty()) {
            return xForwardedFor.split(",")[0].trim();
        }
        String xRealIp = request.getHeader("X-Real-IP");
        if (xRealIp != null && !xRealIp.isEmpty()) {
            return xRealIp;
        }
        return request.getRemoteAddr();
    }
}

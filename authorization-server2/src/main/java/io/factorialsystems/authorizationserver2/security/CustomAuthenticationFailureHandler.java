package io.factorialsystems.authorizationserver2.security;

import io.factorialsystems.authorizationserver2.exception.UserNotVerifiedException;
import io.factorialsystems.authorizationserver2.service.AuditEventPublisher;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.LockedException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.authentication.SimpleUrlAuthenticationFailureHandler;
import org.springframework.stereotype.Component;
import org.springframework.web.util.UriComponentsBuilder;

import java.io.IOException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;

/**
 * Custom authentication failure handler that provides specific error messages
 * for different types of authentication failures and publishes login.failed audit events.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class CustomAuthenticationFailureHandler extends SimpleUrlAuthenticationFailureHandler {

    private final AuditEventPublisher auditEventPublisher;

    @Override
    public void onAuthenticationFailure(HttpServletRequest request, HttpServletResponse response,
                                        AuthenticationException exception) throws IOException, ServletException {

        String username = request.getParameter("username");
        log.warn("Login failed for username: {} - {}", username, exception.getMessage());

        String errorMessage;
        String errorType = "general";
        String userId = null;
        String email = null;

        // Determine the type of authentication failure
        if (exception instanceof UserNotVerifiedException) {
            UserNotVerifiedException unverifiedException = (UserNotVerifiedException) exception;
            errorMessage = "Your email address has not been verified. Please check your email for the verification link.";
            errorType = "unverified";
            userId = unverifiedException.getUserId();
            email = unverifiedException.getEmail();
            log.info("Login attempt with unverified email: {} (user: {})", email, userId);

        } else if (exception instanceof BadCredentialsException) {
            errorMessage = "Invalid username or password. Please try again.";
            errorType = "credentials";

        } else if (exception instanceof DisabledException) {
            errorMessage = "Your account has been disabled. Please contact support for assistance.";
            errorType = "disabled";

        } else if (exception instanceof LockedException) {
            errorMessage = "Your account has been locked. Please contact support for assistance.";
            errorType = "locked";

        } else if (exception instanceof UsernameNotFoundException) {
            // Don't reveal if username exists or not for security
            errorMessage = "Invalid username or password. Please try again.";
            errorType = "credentials";

        } else {
            errorMessage = "An error occurred during login. Please try again.";
            errorType = "general";
            log.error("Unexpected authentication exception for user {}: {}", username, exception.getClass().getName(), exception);
        }

        // Publish login.failed audit event
        try {
            String ipAddress = getClientIp(request);
            auditEventPublisher.publishSecurityEvent(
                    "login.failed",
                    null,  // tenant unknown for failed logins
                    userId,
                    email != null ? email : username,
                    "user",
                    "user",
                    userId,
                    null,
                    Map.of("error_type", errorType, "username_attempted", username != null ? username : ""),
                    Map.of("ip_address", ipAddress, "user_agent", request.getHeader("User-Agent") != null ? request.getHeader("User-Agent") : "")
            );
        } catch (Exception e) {
            // Never break the login flow for audit
        }

        // Build redirect URL with error parameters
        String redirectUrl = buildRedirectUrl(errorMessage, errorType, userId, email, username);

        log.debug("Redirecting to login page with error: type={}, message={}", errorType, errorMessage);

        // Redirect to login page with error
        getRedirectStrategy().sendRedirect(request, response, redirectUrl);
    }

    /**
     * Build the redirect URL with error parameters
     */
    private String buildRedirectUrl(String errorMessage, String errorType, String userId, String email, String username) {
        UriComponentsBuilder builder = UriComponentsBuilder.fromPath("/login")
                .queryParam("error", "true")
                .queryParam("errorType", errorType)
                .queryParam("errorMessage", URLEncoder.encode(errorMessage, StandardCharsets.UTF_8));

        // Add additional parameters for unverified users
        if ("unverified".equals(errorType) && userId != null) {
            builder.queryParam("userId", userId);
            if (email != null) {
                builder.queryParam("email", URLEncoder.encode(email, StandardCharsets.UTF_8));
            }
        }

        // Preserve username for convenience (not for unverified to avoid confusion)
        if (!"unverified".equals(errorType) && username != null && !username.isBlank()) {
            builder.queryParam("username", URLEncoder.encode(username, StandardCharsets.UTF_8));
        }

        return builder.build().toUriString();
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

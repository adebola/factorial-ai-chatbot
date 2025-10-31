package io.factorialsystems.authorizationserver2.exception;

import lombok.Getter;
import org.springframework.security.core.AuthenticationException;

/**
 * Exception thrown when a user attempts to login but their email has not been verified.
 * This allows us to provide specific feedback and offer to resend the verification email.
 */
@Getter
public class UserNotVerifiedException extends AuthenticationException {

    private final String userId;
    private final String email;
    private final String username;

    public UserNotVerifiedException(String message, String userId, String email, String username) {
        super(message);
        this.userId = userId;
        this.email = email;
        this.username = username;
    }

    public UserNotVerifiedException(String message, String userId, String email, String username, Throwable cause) {
        super(message, cause);
        this.userId = userId;
        this.email = email;
        this.username = username;
    }
}

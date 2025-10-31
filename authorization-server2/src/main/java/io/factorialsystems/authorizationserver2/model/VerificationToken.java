package io.factorialsystems.authorizationserver2.model;

import lombok.*;

import java.time.OffsetDateTime;

@Getter
@Setter
@ToString
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class VerificationToken {

    public enum TokenType {
        EMAIL_VERIFICATION,
        PASSWORD_RESET,
        ACCOUNT_ACTIVATION
    }

    private String id;
    private String token;
    private String userId;
    private String email;
    private TokenType tokenType;
    private OffsetDateTime expiresAt;
    private OffsetDateTime usedAt;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;

    // Relationships
    private User user;

    /**
     * Check if the token is expired
     */
    public boolean isExpired() {
        return OffsetDateTime.now().isAfter(expiresAt);
    }

    /**
     * Check if the token has been used
     */
    public boolean isUsed() {
        return usedAt != null;
    }

    /**
     * Check if the token is valid (not expired and not used)
     */
    public boolean isValid() {
        return !isExpired() && !isUsed();
    }

    /**
     * Mark the token as used
     */
    public void markAsUsed() {
        this.usedAt = OffsetDateTime.now();
        this.updatedAt = OffsetDateTime.now();
    }
}
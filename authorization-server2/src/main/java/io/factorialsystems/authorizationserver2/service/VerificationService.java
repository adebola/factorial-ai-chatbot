package io.factorialsystems.authorizationserver2.service;

import io.factorialsystems.authorizationserver2.mapper.VerificationTokenMapper;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.model.VerificationToken;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.security.SecureRandom;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

@Slf4j
@Service
@RequiredArgsConstructor
public class VerificationService {

    private final VerificationTokenMapper verificationTokenMapper;
    private final RedisCacheService cacheService;

    @Value("${authorization.config.security.location:http://localhost:9002/auth}")
    private String baseUrl;

    @Value("${authorization.verification.token.expiry-hours:24}")
    private int tokenExpiryHours;

    @Value("${authorization.verification.token.max-attempts:3}")
    private int maxTokenAttemptsPerHour;

    private static final SecureRandom secureRandom = new SecureRandom();

    /**
     * Generate a new verification token for email verification
     */
    @Transactional
    public VerificationToken generateEmailVerificationToken(String userId, String email) {
        // Check rate limiting - no more than 3 tokens per hour per user
        OffsetDateTime oneHourAgo = OffsetDateTime.now().minusHours(1);
        int recentTokens = verificationTokenMapper.countRecentTokensByUser(
            userId, VerificationToken.TokenType.EMAIL_VERIFICATION, oneHourAgo);

        if (recentTokens >= maxTokenAttemptsPerHour) {
            throw new IllegalStateException("Too many verification tokens requested. Please wait before requesting another.");
        }

        // Invalidate any existing email verification tokens for this user
        verificationTokenMapper.deleteByUserIdAndType(userId, VerificationToken.TokenType.EMAIL_VERIFICATION);

        // Generate secure token
        String token = generateSecureToken();
        OffsetDateTime expiresAt = OffsetDateTime.now().plusHours(tokenExpiryHours);

        VerificationToken verificationToken = VerificationToken.builder()
            .id(UUID.randomUUID().toString())
            .token(token)
            .userId(userId)
            .email(email.toLowerCase().trim())
            .tokenType(VerificationToken.TokenType.EMAIL_VERIFICATION)
            .expiresAt(expiresAt)
            .createdAt(OffsetDateTime.now())
            .updatedAt(OffsetDateTime.now())
            .build();

        int result = verificationTokenMapper.insert(verificationToken);
        if (result <= 0) {
            throw new RuntimeException("Failed to create verification token");
        }

        log.info("Generated email verification token for user: {} (email: {}), expires: {}",
            userId, email, expiresAt);

        return verificationToken;
    }

    /**
     * Verify an email verification token
     */
    @Transactional
    public VerificationResult verifyEmailToken(String token) {
        log.info("Attempting to verify email token: {}", token);

        VerificationToken verificationToken = verificationTokenMapper.findByToken(token);

        if (verificationToken == null) {
            log.warn("Verification token not found: {}", token);
            return VerificationResult.failure("Invalid verification token", null);
        }

        if (verificationToken.isUsed()) {
            log.warn("Verification token already used: {}", token);
            return VerificationResult.failure("This verification link has already been used", null);
        }

        if (verificationToken.isExpired()) {
            log.warn("Verification token expired: {}", token);
            return VerificationResult.failure("This verification link has expired. Please request a new verification email", null);
        }

        // Mark token as used
        verificationToken.markAsUsed();
        verificationTokenMapper.markAsUsed(verificationToken);

        log.info("Successfully validated email verification token for user: {}", verificationToken.getUserId());

        return VerificationResult.success("Your email has been verified successfully! You can now sign in to your account", verificationToken.getUserId());
    }

    /**
     * Generate verification URL for email
     */
    public String generateVerificationUrl(String token) {
        return baseUrl + "/verify-email?token=" + token;
    }

    /**
     * Clean up expired tokens
     */
    @Transactional
    public int cleanupExpiredTokens() {
        OffsetDateTime now = OffsetDateTime.now();
        int deletedCount = verificationTokenMapper.deleteExpiredTokens(now);

        if (deletedCount > 0) {
            log.info("Cleaned up {} expired verification tokens", deletedCount);
        }

        return deletedCount;
    }

    /**
     * Get all verification tokens for a user
     */
    public List<VerificationToken> getTokensByUserId(String userId, VerificationToken.TokenType tokenType) {
        return verificationTokenMapper.findByUserIdAndType(userId, tokenType);
    }

    /**
     * Check if user has pending email verification
     */
    public boolean hasPendingEmailVerification(String userId) {
        List<VerificationToken> tokens = verificationTokenMapper.findByUserIdAndType(
            userId, VerificationToken.TokenType.EMAIL_VERIFICATION);

        return tokens.stream().anyMatch(VerificationToken::isValid);
    }

    /**
     * Generate a new password reset token
     */
    @Transactional
    public VerificationToken createPasswordResetToken(String userId, String email) {
        // Check rate limiting - no more than 3 tokens per hour per email
        OffsetDateTime oneHourAgo = OffsetDateTime.now().minusHours(1);
        int recentTokens = verificationTokenMapper.countRecentTokensByEmail(
            email, VerificationToken.TokenType.PASSWORD_RESET, oneHourAgo);

        if (recentTokens >= maxTokenAttemptsPerHour) {
            throw new IllegalStateException("Too many password reset requests. Please wait before requesting another.");
        }

        // Invalidate any existing password reset tokens for this email
        verificationTokenMapper.deleteByEmailAndType(email, VerificationToken.TokenType.PASSWORD_RESET);

        // Generate secure token
        String token = generateSecureToken();
        OffsetDateTime expiresAt = OffsetDateTime.now().plusHours(tokenExpiryHours);

        VerificationToken verificationToken = VerificationToken.builder()
            .id(UUID.randomUUID().toString())
            .token(token)
            .userId(userId)
            .email(email.toLowerCase().trim())
            .tokenType(VerificationToken.TokenType.PASSWORD_RESET)
            .expiresAt(expiresAt)
            .createdAt(OffsetDateTime.now())
            .updatedAt(OffsetDateTime.now())
            .build();

        int result = verificationTokenMapper.insert(verificationToken);
        if (result <= 0) {
            throw new RuntimeException("Failed to create password reset token");
        }

        log.info("Generated password reset token for email: {}, expires: {}", email, expiresAt);

        return verificationToken;
    }

    /**
     * Validate a password reset token
     */
    @Transactional
    public VerificationResult validatePasswordResetToken(String token) {
        log.info("Attempting to validate password reset token: {}", token);

        VerificationToken verificationToken = verificationTokenMapper.findByToken(token);

        if (verificationToken == null) {
            log.warn("Password reset token not found: {}", token);
            return VerificationResult.failure("Invalid reset link", null);
        }

        if (verificationToken.getTokenType() != VerificationToken.TokenType.PASSWORD_RESET) {
            log.warn("Token is not a password reset token: {}", token);
            return VerificationResult.failure("Invalid reset link", null);
        }

        if (verificationToken.isUsed()) {
            log.warn("Password reset token already used: {}", token);
            return VerificationResult.failure("This reset link has already been used", null);
        }

        if (verificationToken.isExpired()) {
            log.warn("Password reset token expired: {}", token);
            return VerificationResult.failure("This reset link has expired. Please request a new password reset", null);
        }

        log.info("Successfully validated password reset token for email: {}", verificationToken.getEmail());

        return VerificationResult.success("Token is valid", verificationToken.getEmail());
    }

    /**
     * Get verification token by token string (for password reset validation)
     */
    public VerificationToken getTokenByString(String token) {
        return verificationTokenMapper.findByToken(token);
    }

    /**
     * Mark a password reset token as used
     */
    @Transactional
    public void markPasswordResetTokenAsUsed(String token) {
        VerificationToken verificationToken = verificationTokenMapper.findByToken(token);
        if (verificationToken != null) {
            verificationToken.markAsUsed();
            verificationTokenMapper.markAsUsed(verificationToken);
            log.info("Marked password reset token as used for email: {}", verificationToken.getEmail());
        }
    }

    /**
     * Generate password reset URL
     */
    public String generatePasswordResetUrl(String token) {
        return baseUrl + "/reset-password?token=" + token;
    }

    /**
     * Generate a cryptographically secure token
     */
    private String generateSecureToken() {
        byte[] tokenBytes = new byte[32]; // 256 bits
        secureRandom.nextBytes(tokenBytes);

        // Convert to hex string
        StringBuilder token = new StringBuilder();
        for (byte b : tokenBytes) {
            token.append(String.format("%02x", b));
        }

        return token.toString();
    }

    /**
     * Result class for verification operations
     */
    public static class VerificationResult {
        private final boolean success;
        private final String message;
        private final String userId;

        private VerificationResult(boolean success, String message, String userId) {
            this.success = success;
            this.message = message;
            this.userId = userId;
        }

        public static VerificationResult success(String message, String userId) {
            return new VerificationResult(true, message, userId);
        }

        public static VerificationResult failure(String message, String userId) {
            return new VerificationResult(false, message, userId);
        }

        public boolean isSuccess() {
            return success;
        }

        public String getMessage() {
            return message;
        }

        public String getUserId() {
            return userId;
        }
    }
}
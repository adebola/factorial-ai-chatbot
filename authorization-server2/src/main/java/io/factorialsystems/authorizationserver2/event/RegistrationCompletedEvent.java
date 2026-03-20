package io.factorialsystems.authorizationserver2.event;

import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.model.VerificationToken;
import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * Event published inside the registration transaction, consumed after commit.
 * Carries all data needed for post-commit side effects (RabbitMQ, Redis, email).
 */
@Getter
@RequiredArgsConstructor
public class RegistrationCompletedEvent {
    private final Tenant tenant;
    private final User user;
    private final VerificationToken verificationToken; // nullable if token generation failed
}

package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.model.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.time.OffsetDateTime;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

/**
 * Integration test for EmailNotificationService that sends actual messages to RabbitMQ.
 * These tests will result in real emails being sent via the communications service.
 *
 * To run these tests:
 * 1. Ensure RabbitMQ is running locally
 * 2. Ensure the communications service is running and connected to RabbitMQ
 * 3. Configure valid email credentials in the communications service
 *
 * Note: These tests are marked with @SpringBootTest which loads the full application context
 */
@SpringBootTest
@TestPropertySource(properties = {
    "spring.rabbitmq.host=localhost",
    "spring.rabbitmq.port=5672",
    "spring.rabbitmq.username=guest",
    "spring.rabbitmq.password=guest",
    "authorization.config.rabbitmq.exchange.name=topic-exchange",
    "authorization.config.rabbitmq.key.email-notification=email.notification",
    "authorization.config.security.location=http://localhost:9002/auth",
    "spring.datasource.url=jdbc:h2:mem:testdb",
    "spring.datasource.driver-class-name=org.h2.Driver",
    "spring.jpa.hibernate.ddl-auto=create-drop",
    "mybatis.mapper-locations=classpath:mapper/*.xml"
})
public class EmailNotificationServiceIntegrationTest {

    @Autowired
    private EmailNotificationService emailNotificationService;

    @Autowired
    private RabbitTemplate rabbitTemplate;

    @Autowired
    private ObjectMapper objectMapper;

    @Value("${authorization.config.security.location:http://localhost:9002/auth}")
    private String baseUrl;

    private User testUser;

    @BeforeEach
    void setUp() {
        // Create a test user with real email address
        // UPDATE THIS EMAIL ADDRESS to where you want to receive test emails
        testUser = User.builder()
                .id(UUID.randomUUID().toString())
                .tenantId("test-tenant-" + UUID.randomUUID().toString())
                .username("testuser_" + System.currentTimeMillis())
                .email("adebola@factorialsystems.io") // Change this to your test email
                .firstName("Test")
                .lastName("User")
                .isActive(true)
                .isEmailVerified(false)
                .createdAt(OffsetDateTime.now())
                .updatedAt(OffsetDateTime.now())
                .build();
    }

    /**
     * Integration test that sends a real email verification message.
     * This will trigger the communications service to send an actual email.
     */
    @Test
    void sendEmailVerification_IntegrationTest() {
        // Given
        String verificationToken = UUID.randomUUID().toString();

        System.out.println("========================================");
        System.out.println("Sending Email Verification");
        System.out.println("========================================");
        System.out.println("To: " + testUser.getEmail());
        System.out.println("Token: " + verificationToken);
        System.out.println("Verification URL: " + baseUrl + "/verify-email?token=" + verificationToken);
        System.out.println("========================================");

        // When - This will send a real message to RabbitMQ
        assertDoesNotThrow(() ->
            emailNotificationService.sendEmailVerification(testUser, verificationToken)
        );

        // Then
        System.out.println("✅ Email verification message sent successfully to RabbitMQ");
        System.out.println("Check the communications service logs for processing details");
        System.out.println("Check the email inbox for: " + testUser.getEmail());

        // Give the message some time to be processed
        try {
            Thread.sleep(2000); // Wait 2 seconds for message to be processed
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        // Note: In a real integration test, you might want to:
        // 1. Check RabbitMQ management console to verify message was published
        // 2. Query the communications service database to verify email was logged
        // 3. Use a test email service to verify email was received
    }

    /**
     * Integration test that sends a real welcome email message.
     * This will trigger the communications service to send an actual email.
     */
    @Test
    void sendWelcomeEmail_IntegrationTest() {
        // Given
        testUser.setIsEmailVerified(true); // User is now verified

        System.out.println("========================================");
        System.out.println("Sending Welcome Email");
        System.out.println("========================================");
        System.out.println("To: " + testUser.getEmail());
        System.out.println("Name: " + testUser.getFirstName() + " " + testUser.getLastName());
        System.out.println("Login URL: " + baseUrl + "/login");
        System.out.println("========================================");

        // When - This will send a real message to RabbitMQ
        assertDoesNotThrow(() ->
            emailNotificationService.sendWelcomeEmail(testUser)
        );

        // Then
        System.out.println("✅ Welcome email message sent successfully to RabbitMQ");
        System.out.println("Check the communications service logs for processing details");
        System.out.println("Check the email inbox for: " + testUser.getEmail());

        // Give the message some time to be processed
        try {
            Thread.sleep(2000); // Wait 2 seconds for message to be processed
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /**
     * Test sending multiple emails in sequence to verify the system can handle load.
     * This will send both verification and welcome emails.
     */
    @Test
    void sendMultipleEmails_IntegrationTest() {
        System.out.println("========================================");
        System.out.println("Sending Multiple Emails Test");
        System.out.println("========================================");

        // Send verification email
        String verificationToken = UUID.randomUUID().toString();
        assertDoesNotThrow(() ->
            emailNotificationService.sendEmailVerification(testUser, verificationToken)
        );
        System.out.println("✅ Verification email sent");

        // Simulate user verification
        testUser.setIsEmailVerified(true);

        // Wait a bit
        try {
            Thread.sleep(1000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        // Send welcome email
        assertDoesNotThrow(() ->
            emailNotificationService.sendWelcomeEmail(testUser)
        );
        System.out.println("✅ Welcome email sent");

        System.out.println("========================================");
        System.out.println("Multiple emails test completed");
        System.out.println("Check inbox for 2 emails at: " + testUser.getEmail());
        System.out.println("========================================");

        // Wait for processing
        try {
            Thread.sleep(3000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /**
     * Test with different user data to verify template rendering with various inputs.
     */
    @Test
    void sendEmailWithSpecialCharacters_IntegrationTest() {
        // Create user with special characters in name
        User userWithSpecialChars = User.builder()
                .id(UUID.randomUUID().toString())
                .tenantId("test-tenant-" + UUID.randomUUID().toString())
                .username("special_user")
                .email("adebola@factorialsystems.io") // Change this to your test email
                .firstName("José")
                .lastName("O'Brien-Smith")
                .isActive(true)
                .isEmailVerified(false)
                .createdAt(OffsetDateTime.now())
                .build();

        String verificationToken = UUID.randomUUID().toString();

        System.out.println("========================================");
        System.out.println("Testing with Special Characters");
        System.out.println("========================================");
        System.out.println("Name: " + userWithSpecialChars.getFirstName() + " " + userWithSpecialChars.getLastName());
        System.out.println("========================================");

        // Send email with special characters
        assertDoesNotThrow(() ->
            emailNotificationService.sendEmailVerification(userWithSpecialChars, verificationToken)
        );

        System.out.println("✅ Email with special characters sent successfully");

        // Wait for processing
        try {
            Thread.sleep(2000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    /**
     * Performance test - send multiple emails rapidly to test system throughput.
     * WARNING: This will send multiple real emails. Use with caution.
     */
    @Test
    void performanceTest_SendMultipleEmailsRapidly() {
        int numberOfEmails = 5; // Adjust as needed

        System.out.println("========================================");
        System.out.println("Performance Test - Sending " + numberOfEmails + " emails");
        System.out.println("========================================");

        long startTime = System.currentTimeMillis();

        for (int i = 0; i < numberOfEmails; i++) {
            User user = User.builder()
                    .id(UUID.randomUUID().toString())
                    .tenantId("test-tenant-" + UUID.randomUUID().toString())
                    .username("perftest_user_" + i)
                    .email("adebola+test" + i + "@factorialsystems.io") // Using + addressing for testing
                    .firstName("PerfTest")
                    .lastName("User" + i)
                    .isActive(true)
                    .isEmailVerified(false)
                    .createdAt(OffsetDateTime.now())
                    .build();

            String token = UUID.randomUUID().toString();

            try {
                emailNotificationService.sendEmailVerification(user, token);
                System.out.println("✅ Email " + (i + 1) + " sent to: " + user.getEmail());
            } catch (Exception e) {
                System.err.println("❌ Failed to send email " + (i + 1) + ": " + e.getMessage());
            }
        }

        long endTime = System.currentTimeMillis();
        long duration = endTime - startTime;

        System.out.println("========================================");
        System.out.println("Performance Test Results:");
        System.out.println("Total emails sent: " + numberOfEmails);
        System.out.println("Total time: " + duration + "ms");
        System.out.println("Average time per email: " + (duration / numberOfEmails) + "ms");
        System.out.println("========================================");

        // Wait for all messages to be processed
        try {
            Thread.sleep(5000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
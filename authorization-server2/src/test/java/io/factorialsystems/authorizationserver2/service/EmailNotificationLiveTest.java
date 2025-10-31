package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.dto.EmailNotificationRequest;
import io.factorialsystems.authorizationserver2.model.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.connection.ConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

import java.time.OffsetDateTime;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Live test for EmailNotificationService that directly publishes to RabbitMQ.
 * This test doesn't require Spring Boot context and connects directly to RabbitMQ.
 *
 * Prerequisites:
 * 1. RabbitMQ must be running on localhost:5672 (default guest/guest credentials)
 * 2. Communications service should be running to process the messages
 *
 * To run this test:
 * - Just run it as a regular JUnit test from your IDE
 * - No special Spring configuration needed
 */
public class EmailNotificationLiveTest {

    private RabbitTemplate rabbitTemplate;
    private ObjectMapper objectMapper;
    private final String exchangeName = "topic-exchange";
    private final String emailRoutingKey = "email.notification";
    private final String baseUrl = "http://localhost:9002/auth";

    @BeforeEach
    void setUp() {
        // Create RabbitMQ connection factory with default guest credentials
        CachingConnectionFactory connectionFactory = new CachingConnectionFactory();
        connectionFactory.setHost("localhost");
        connectionFactory.setPort(5672);
        connectionFactory.setUsername("guest");
        connectionFactory.setPassword("guest");

        // Create RabbitTemplate
        rabbitTemplate = new RabbitTemplate(connectionFactory);

        // Create ObjectMapper
        objectMapper = new ObjectMapper();
    }

    @Test
    void sendRealEmailVerification() throws Exception {
        System.out.println("========================================");
        System.out.println("SENDING REAL EMAIL VERIFICATION");
        System.out.println("========================================");

        // Create test user
        User testUser = User.builder()
                .id(UUID.randomUUID().toString())
                .tenantId("test-tenant-" + UUID.randomUUID())
                .username("testuser_" + System.currentTimeMillis())
                .email("adebola@factorialsystems.io") // UPDATE THIS to your email
                .firstName("Test")
                .lastName("User")
                .isActive(true)
                .isEmailVerified(false)
                .createdAt(OffsetDateTime.now())
                .build();

        String verificationToken = UUID.randomUUID().toString();
        String verificationUrl = baseUrl + "/verify-email?token=" + verificationToken;

        // Create template data
        Map<String, Object> templateData = new HashMap<>();
        templateData.put("firstName", testUser.getFirstName());
        templateData.put("lastName", testUser.getLastName());
        templateData.put("email", testUser.getEmail());
        templateData.put("verificationUrl", verificationUrl);
        templateData.put("baseUrl", baseUrl);

        // Create email notification request
        EmailNotificationRequest request = EmailNotificationRequest.builder()
                .tenantId(testUser.getTenantId())
                .toEmail(testUser.getEmail())
                .toName(testUser.getFirstName() + " " + testUser.getLastName())
                .subject("Verify Your Email Address - ChatCraft")
                .htmlContent(generateVerificationHtml(testUser.getFirstName(), verificationUrl))
                .textContent(generateVerificationText(testUser.getFirstName(), verificationUrl))
                .template(EmailNotificationRequest.EmailTemplate.builder()
                        .templateName("email_verification")
                        .type(EmailNotificationRequest.EmailTemplate.TemplateType.EMAIL_VERIFICATION)
                        .build())
                .templateData(templateData)
                .build();

        // Serialize to JSON
        String jsonMessage = objectMapper.writeValueAsString(request);

        System.out.println("Sending to RabbitMQ:");
        System.out.println("  Exchange: " + exchangeName);
        System.out.println("  Routing Key: " + emailRoutingKey);
        System.out.println("  To: " + testUser.getEmail());
        System.out.println("  Token: " + verificationToken);
        System.out.println("  URL: " + verificationUrl);

        // Send to RabbitMQ
        rabbitTemplate.convertAndSend(exchangeName, emailRoutingKey, jsonMessage);

        System.out.println("✅ Message sent to RabbitMQ successfully!");
        System.out.println("Check the communications service logs and your email inbox.");

        // Wait a bit for processing
        Thread.sleep(3000);
    }

    @Test
    void sendRealWelcomeEmail() throws Exception {
        System.out.println("========================================");
        System.out.println("SENDING REAL WELCOME EMAIL");
        System.out.println("========================================");

        // Create test user
        User testUser = User.builder()
                .id(UUID.randomUUID().toString())
                .tenantId("test-tenant-" + UUID.randomUUID())
                .username("welcomeuser_" + System.currentTimeMillis())
                .email("adebola@factorialsystems.io") // UPDATE THIS to your email
                .firstName("Welcome")
                .lastName("User")
                .isActive(true)
                .isEmailVerified(true)
                .createdAt(OffsetDateTime.now())
                .build();

        String loginUrl = baseUrl + "/login";

        // Create template data
        Map<String, Object> templateData = new HashMap<>();
        templateData.put("firstName", testUser.getFirstName());
        templateData.put("lastName", testUser.getLastName());
        templateData.put("email", testUser.getEmail());
        templateData.put("loginUrl", loginUrl);
        templateData.put("baseUrl", baseUrl);

        // Create email notification request
        EmailNotificationRequest request = EmailNotificationRequest.builder()
                .tenantId(testUser.getTenantId())
                .toEmail(testUser.getEmail())
                .toName(testUser.getFirstName() + " " + testUser.getLastName())
                .subject("Welcome to ChatCraft!")
                .htmlContent(generateWelcomeHtml(testUser.getFirstName(), loginUrl))
                .textContent(generateWelcomeText(testUser.getFirstName(), loginUrl))
                .template(EmailNotificationRequest.EmailTemplate.builder()
                        .templateName("welcome")
                        .type(EmailNotificationRequest.EmailTemplate.TemplateType.WELCOME)
                        .build())
                .templateData(templateData)
                .build();

        // Serialize to JSON
        String jsonMessage = objectMapper.writeValueAsString(request);

        System.out.println("Sending to RabbitMQ:");
        System.out.println("  Exchange: " + exchangeName);
        System.out.println("  Routing Key: " + emailRoutingKey);
        System.out.println("  To: " + testUser.getEmail());
        System.out.println("  Login URL: " + loginUrl);

        // Send to RabbitMQ
        rabbitTemplate.convertAndSend(exchangeName, emailRoutingKey, jsonMessage);

        System.out.println("✅ Message sent to RabbitMQ successfully!");
        System.out.println("Check the communications service logs and your email inbox.");

        // Wait a bit for processing
        Thread.sleep(3000);
    }

    private String generateVerificationHtml(String firstName, String verificationUrl) {
        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Verify Your Email</title>
                <style>
                    body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
                    .button { display: inline-block; background: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; }
                </style>
            </head>
            <body>
                <h1>ChatCraft</h1>
                <h2>Verify Your Email Address</h2>
                <p>Hello %s,</p>
                <p>Thank you for registering! Please verify your email by clicking below:</p>
                <p><a href="%s" class="button">Verify Email Address</a></p>
                <p>Or copy this link: %s</p>
                <p>This link expires in 24 hours.</p>
            </body>
            </html>
            """, firstName, verificationUrl, verificationUrl);
    }

    private String generateVerificationText(String firstName, String verificationUrl) {
        return String.format("""
            ChatCraft - Verify Your Email

            Hello %s,

            Thank you for registering! Please verify your email by visiting:

            %s

            This link expires in 24 hours.

            Best regards,
            The ChatCraft Team
            """, firstName, verificationUrl);
    }

    private String generateWelcomeHtml(String firstName, String loginUrl) {
        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Welcome to ChatCraft</title>
                <style>
                    body { font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }
                    .button { display: inline-block; background: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; }
                </style>
            </head>
            <body>
                <h1>ChatCraft</h1>
                <h2>Welcome!</h2>
                <p>Hello %s,</p>
                <p>Your email has been verified and your account is now active!</p>
                <p><a href="%s" class="button">Sign In to ChatCraft</a></p>
            </body>
            </html>
            """, firstName, loginUrl);
    }

    private String generateWelcomeText(String firstName, String loginUrl) {
        return String.format("""
            ChatCraft - Welcome!

            Hello %s,

            Your email has been verified and your account is now active!

            Sign in here: %s

            Best regards,
            The ChatCraft Team
            """, firstName, loginUrl);
    }
}
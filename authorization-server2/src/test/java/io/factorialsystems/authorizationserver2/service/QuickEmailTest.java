package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.dto.EmailNotificationRequest;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

/**
 * Quick standalone test to send a real email through RabbitMQ.
 * Run this as a main method - no Spring context required.
 *
 * Prerequisites:
 * 1. RabbitMQ running on localhost:5672
 * 2. Communications service running to process messages
 */
public class QuickEmailTest {

    public static void main(String[] args) {
        System.out.println("🚀 Starting Quick Email Test");

        try {
            String host = System.getenv().getOrDefault("RABBITMQ_HOST", "localhost");
            int port = Integer.parseInt(System.getenv().getOrDefault("RABBITMQ_PORT", "5672"));
            String username = System.getenv().getOrDefault("RABBITMQ_USERNAME", "user");
            String password = System.getenv().getOrDefault("RABBITMQ_PASSWORD", "password");
            String virtualHost = System.getenv().getOrDefault("RABBITMQ_VHOST", "/");
            String exchange = System.getenv().getOrDefault("RABBITMQ_EXCHANGE", "topic-exchange");
            String routingKey = System.getenv().getOrDefault("RABBITMQ_EMAIL_ROUTING_KEY", "email.notification");

            System.out.println("📋 RabbitMQ Configuration:");
            System.out.printf("  Host: %s%n", host);
            System.out.printf("  Port: %d%n", port);
            System.out.printf("  Username: %s%n", username);
            System.out.printf("  Virtual Host: %s%n", virtualHost);
            System.out.printf("  Exchange: %s%n", exchange);
            System.out.printf("  Routing Key: %s%n", routingKey);

            // Setup RabbitMQ connection
            CachingConnectionFactory connectionFactory = new CachingConnectionFactory();
            connectionFactory.setHost(host);
            connectionFactory.setPort(port);
            connectionFactory.setUsername(username);
            connectionFactory.setPassword(password);
            connectionFactory.setVirtualHost(virtualHost);

            RabbitTemplate rabbitTemplate = new RabbitTemplate(connectionFactory);
            ObjectMapper objectMapper = new ObjectMapper();

            // Test connection
            System.out.println("📡 Testing RabbitMQ connection...");
            rabbitTemplate.execute(channel -> {
                System.out.println("✅ Connected to RabbitMQ successfully!");
                return null;
            });

            // Create email request
            String testEmail = "adebola@factorialsystems.io"; // UPDATE THIS
            String verificationToken = UUID.randomUUID().toString();
            String verificationUrl = "http://localhost:9002/auth/verify-email?token=" + verificationToken;

            Map<String, Object> templateData = new HashMap<>();
            templateData.put("firstName", "Test");
            templateData.put("lastName", "User");
            templateData.put("email", testEmail);
            templateData.put("verificationUrl", verificationUrl);
            templateData.put("baseUrl", "http://localhost:9002/auth");

            EmailNotificationRequest request = EmailNotificationRequest.builder()
                    .tenantId("quick-test-tenant")
                    .toEmail(testEmail)
                    .toName("Test User")
                    .subject("Test Email from Authorization Server")
                    .htmlContent(createTestHtml("Test", verificationUrl))
                    .textContent(createTestText("Test", verificationUrl))
                    .template(EmailNotificationRequest.EmailTemplate.builder()
                            .templateName("email_verification")
                            .type(EmailNotificationRequest.EmailTemplate.TemplateType.EMAIL_VERIFICATION)
                            .build())
                    .templateData(templateData)
                    .build();

            // Send to RabbitMQ
            String jsonMessage = objectMapper.writeValueAsString(request);

            System.out.println("📧 Sending email message...");
            System.out.println("  To: " + testEmail);
            System.out.println("  Token: " + verificationToken);
            System.out.println("  Exchange: " + exchange);
            System.out.println("  Routing Key: " + routingKey);

            rabbitTemplate.convertAndSend(exchange, routingKey, jsonMessage);

            System.out.println("Email message sent to RabbitMQ!");
            System.out.println("📬 Check your inbox at: " + testEmail);
            System.out.println("🔍 Check communications service logs for processing");

            // Close connection
            connectionFactory.destroy();

            System.out.println("🎉 Test completed successfully!");

        } catch (Exception e) {
            System.err.println("❌ Error: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private static String createTestHtml(String firstName, String verificationUrl) {
        return String.format("""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <title>Test Email</title>
                <style>
                    body {
                        font-family: Arial, sans-serif;
                        max-width: 600px;
                        margin: 0 auto;
                        padding: 20px;
                        background: #f5f5f5;
                    }
                    .container {
                        background: white;
                        padding: 30px;
                        border-radius: 8px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }
                    .button {
                        display: inline-block;
                        background: #007bff;
                        color: white;
                        padding: 12px 30px;
                        text-decoration: none;
                        border-radius: 5px;
                        margin: 20px 0;
                    }
                    .footer {
                        text-align: center;
                        color: #666;
                        font-size: 14px;
                        margin-top: 30px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <h1 style="color: #333;"> Test Email from Authorization Server</h1>
                    <p>Hello %s,</p>
                    <p>This is a test email sent from the Authorization Server through RabbitMQ to the Communications Service.</p>
                    <p>If you receive this email, it means the integration is working correctly!</p>
                    <p style="text-align: center;">
                        <a href="%s" class="button">Test Verification Link</a>
                    </p>
                    <p><strong>Technical Details:</strong></p>
                    <ul>
                        <li>Source: Authorization Server</li>
                        <li>Transport: RabbitMQ (topic-exchange)</li>
                        <li>Processor: Communications Service</li>
                        <li>Routing Key: email.notification</li>
                    </ul>
                    <p>Test URL: <code>%s</code></p>
                </div>
                <div class="footer">
                    <p>This is an automated test email from ChatCraft Authorization Server</p>
                </div>
            </body>
            </html>
            """, firstName, verificationUrl, verificationUrl);
    }

    private static String createTestText(String firstName, String verificationUrl) {
        return String.format("""
            TEST EMAIL FROM AUTHORIZATION SERVER

            Hello %s,

            This is a test email sent from the Authorization Server through RabbitMQ
            to the Communications Service.

            If you receive this email, the integration is working correctly!

            Test verification link: %s

            Technical Details:
            - Source: Authorization Server
            - Transport: RabbitMQ (topic-exchange)
            - Processor: Communications Service
            - Routing Key: email.notification

            Best regards,
            ChatCraft Authorization Server Test
            """, firstName, verificationUrl);
    }
}
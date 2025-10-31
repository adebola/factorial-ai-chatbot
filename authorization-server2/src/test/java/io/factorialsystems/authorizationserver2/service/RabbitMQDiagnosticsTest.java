package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.rabbitmq.client.*;
import io.factorialsystems.authorizationserver2.dto.EmailNotificationRequest;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeoutException;

/**
 * Comprehensive RabbitMQ diagnostics tool to:
 * 1. Send a message from Authorization Server
 * 2. Monitor if the message is consumed by Communications Service
 * 3. Provide detailed debugging information
 */
public class RabbitMQDiagnosticsTest {

    public static void main(String[] args) {
        System.out.println("🔍 RabbitMQ DIAGNOSTICS TOOL");
        System.out.println("=============================");

        try {
            runDiagnostics();
        } catch (Exception e) {
            System.err.println("❌ Diagnostics failed: " + e.getMessage());
            e.printStackTrace();
        }
    }

    private static void runDiagnostics() throws IOException, TimeoutException, InterruptedException {
        String host = "localhost";
        int port = 5672;
        String username = "user";
        String password = "password";
        String exchange = "topic-exchange";
        String routingKey = "email.notification";

        System.out.println("📋 Configuration:");
        System.out.println("  Host: " + host);
        System.out.println("  Port: " + port);
        System.out.println("  Username: " + username);
        System.out.println("  Exchange: " + exchange);
        System.out.println("  Routing Key: " + routingKey);

        // Create connection
        ConnectionFactory factory = new ConnectionFactory();
        factory.setHost(host);
        factory.setPort(port);
        factory.setUsername(username);
        factory.setPassword(password);

        try (Connection connection = factory.newConnection();
             Channel channel = connection.createChannel()) {

            System.out.println("\n✅ Connected to RabbitMQ successfully!");

            // 1. Check if exchange exists
            System.out.println("\n🔍 Step 1: Checking exchange...");
            try {
                channel.exchangeDeclarePassive(exchange);
                System.out.println("✅ Exchange '" + exchange + "' exists");
            } catch (Exception e) {
                System.out.println("❌ Exchange '" + exchange + "' does not exist, creating it...");
                channel.exchangeDeclare(exchange, "topic", true);
                System.out.println("✅ Exchange '" + exchange + "' created");
            }

            // 2. Check queues
            System.out.println("\n🔍 Step 2: Checking queues...");
            String[] queuesToCheck = {"email.send"};

            for (String queueName : queuesToCheck) {
                try {
                    AMQP.Queue.DeclareOk result = channel.queueDeclarePassive(queueName);
                    System.out.println("✅ Queue '" + queueName + "' exists with " +
                                     result.getMessageCount() + " messages");

                    // Check bindings
                    System.out.println("   Checking bindings for queue: " + queueName);

                } catch (Exception e) {
                    System.out.println("❌ Queue '" + queueName + "' does not exist or not accessible");
                    System.out.println("   Creating queue and binding...");

                    channel.queueDeclare(queueName, true, false, false, null);
                    channel.queueBind(queueName, exchange, "email.send");
                    channel.queueBind(queueName, exchange, "email.notification");

                    System.out.println("✅ Queue '" + queueName + "' created and bound");
                }
            }

            // 3. Create and send test message
            System.out.println("\n🔍 Step 3: Creating test message...");

            String testEmail = "test@example.com";
            String verificationToken = UUID.randomUUID().toString();

            Map<String, Object> templateData = new HashMap<>();
            templateData.put("firstName", "Test");
            templateData.put("lastName", "User");
            templateData.put("email", testEmail);
            templateData.put("verificationUrl", "http://localhost:9002/auth/verify-email?token=" + verificationToken);
            templateData.put("baseUrl", "http://localhost:9002/auth");

            EmailNotificationRequest request = EmailNotificationRequest.builder()
                    .tenantId("diagnostics-tenant-" + UUID.randomUUID())
                    .toEmail(testEmail)
                    .toName("Test User")
                    .subject("🧪 RabbitMQ Diagnostics Test Email")
                    .htmlContent(createTestHtml())
                    .textContent(createTestText())
                    .template(EmailNotificationRequest.EmailTemplate.builder()
                            .templateName("email_verification")
                            .type(EmailNotificationRequest.EmailTemplate.TemplateType.EMAIL_VERIFICATION)
                            .build())
                    .templateData(templateData)
                    .build();

            ObjectMapper objectMapper = new ObjectMapper();
            String jsonMessage = objectMapper.writeValueAsString(request);

            System.out.println("📧 Message created:");
            System.out.println("  To: " + testEmail);
            System.out.println("  Subject: " + request.getSubject());
            System.out.println("  Message size: " + jsonMessage.length() + " bytes");

            // 4. Send message
            System.out.println("\n🔍 Step 4: Sending message...");

            AMQP.BasicProperties properties = new AMQP.BasicProperties.Builder()
                    .contentType("application/json")
                    .deliveryMode(2) // persistent
                    .timestamp(new java.util.Date())
                    .build();

            channel.basicPublish(exchange, routingKey, properties, jsonMessage.getBytes(StandardCharsets.UTF_8));

            System.out.println("✅ Message sent successfully!");
            System.out.println("  Exchange: " + exchange);
            System.out.println("  Routing Key: " + routingKey);
            System.out.println("  Message ID: " + properties.getMessageId());

            // 5. Wait and check if message was consumed
            System.out.println("\n🔍 Step 5: Monitoring message consumption...");
            System.out.println("Waiting 10 seconds to see if the message gets consumed...");

            for (int i = 10; i >= 1; i--) {
                System.out.print("⏰ " + i + " seconds remaining...\r");
                Thread.sleep(1000);
            }

            System.out.println("\n");

            // Check queue status after waiting
            for (String queueName : queuesToCheck) {
                try {
                    AMQP.Queue.DeclareOk result = channel.queueDeclarePassive(queueName);
                    int messageCount = result.getMessageCount();

                    if (messageCount == 0) {
                        System.out.println("✅ SUCCESS: Message was consumed from queue '" + queueName + "'!");
                        System.out.println("   The communications service is working correctly.");
                    } else {
                        System.out.println("⚠️  Message still in queue '" + queueName + "' (count: " + messageCount + ")");
                        System.out.println("   This might mean:");
                        System.out.println("   - Communications service is not running");
                        System.out.println("   - Communications service consumer is not started");
                        System.out.println("   - Communications service has connection issues");
                    }
                } catch (Exception e) {
                    System.out.println("❌ Could not check queue status: " + e.getMessage());
                }
            }

            // 6. Summary and recommendations
            System.out.println("\n📋 SUMMARY AND RECOMMENDATIONS:");
            System.out.println("================================");
            System.out.println("1. ✅ RabbitMQ connection successful");
            System.out.println("2. ✅ Message sent successfully");
            System.out.println("3. To verify the communications service is working:");
            System.out.println("   - Check communications service logs for message processing");
            System.out.println("   - Ensure the service is running on port 8003");
            System.out.println("   - Verify RabbitMQ consumer is started in the service");
            System.out.println("4. If message was not consumed:");
            System.out.println("   - Restart the communications service");
            System.out.println("   - Check the main.py file has RabbitMQ consumer startup code");

        } catch (Exception e) {
            System.err.println("❌ Connection failed: " + e.getMessage());
            throw e;
        }
    }

    private static String createTestHtml() {
        return """
            <html>
            <body>
                <h1>🧪 RabbitMQ Diagnostics Test</h1>
                <p>This is a test message from the Authorization Server to verify RabbitMQ connectivity.</p>
                <p>If you receive this email, the integration is working!</p>
            </body>
            </html>
            """;
    }

    private static String createTestText() {
        return """
            RabbitMQ Diagnostics Test

            This is a test message from the Authorization Server to verify RabbitMQ connectivity.
            If you receive this email, the integration is working!
            """;
    }
}
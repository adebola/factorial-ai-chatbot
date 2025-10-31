package io.factorialsystems.authorizationserver2.service;

import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitTemplate;

/**
 * Simple RabbitMQ connection test to help diagnose connection issues.
 * This will try different credential combinations to find what works.
 */
public class RabbitMQConnectionTest {

    public static void main(String[] args) {
        System.out.println("🔍 Testing RabbitMQ Connection Options");
        System.out.println("=====================================");

        // Test different credential combinations
        String[][] credentialOptions = {
            {"guest", "guest"},           // Default RabbitMQ
            {"user", "password"},         // From your application.yml
            {"", ""},                     // Empty credentials
            {"rabbit_user", "rabbit_password"}, // Alternative
        };

        for (String[] creds : credentialOptions) {
            testConnection("localhost", 5672, creds[0], creds[1]);
        }

        System.out.println("\n🔍 Testing with environment variables...");
        String envUser = System.getenv().getOrDefault("RABBITMQ_USERNAME", "user");
        String envPass = System.getenv().getOrDefault("RABBITMQ_PASSWORD", "password");
        testConnection("localhost", 5672, envUser, envPass);
    }

    private static void testConnection(String host, int port, String username, String password) {
        System.out.printf("\n📡 Testing: %s:%d with user='%s', pass='%s'%n",
                         host, port, username, password.replaceAll(".", "*"));

        try {
            CachingConnectionFactory factory = new CachingConnectionFactory();
            factory.setHost(host);
            factory.setPort(port);
            factory.setUsername(username);
            factory.setPassword(password);
            factory.setConnectionTimeout(5000); // 5 second timeout

            RabbitTemplate template = new RabbitTemplate(factory);

            template.execute(channel -> {
                System.out.println("✅ SUCCESS: Connected to RabbitMQ!");
                System.out.println("   Connection: " + channel.getConnection());
                System.out.println("   Virtual Host: " + channel.getConnection().getAddress());
                return null;
            });

            // Test sending a simple message to default exchange
            try {
                template.convertAndSend("", "test.queue", "Test message from authorization server");
                System.out.println("✅ SUCCESS: Message sent successfully!");
            } catch (Exception e) {
                System.out.println("⚠️  Connection OK but sending failed: " + e.getMessage());
            }

            factory.destroy();

        } catch (Exception e) {
            System.out.println("❌ FAILED: " + e.getMessage());

            // Print more detailed error for debugging
            if (e.getCause() != null) {
                System.out.println("   Cause: " + e.getCause().getMessage());
            }
        }
    }
}
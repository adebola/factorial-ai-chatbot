package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.model.User;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Profile;

import java.time.OffsetDateTime;
import java.util.Scanner;
import java.util.UUID;

/**
 * Manual test runner for EmailNotificationService.
 * This class can be run as a standalone Spring Boot application to test email sending.
 *
 * To run:
 * 1. Ensure RabbitMQ is running locally
 * 2. Ensure the communications service is running
 * 3. Run this class as a Java application
 * 4. Follow the interactive prompts
 *
 * You can also run it from command line:
 * mvn spring-boot:run -Dspring-boot.run.main-class=io.factorialsystems.authorizationserver2.service.EmailNotificationManualTest
 */
@SpringBootApplication
@ComponentScan(basePackages = "io.factorialsystems.authorizationserver2")
@Profile("manual-test")
public class EmailNotificationManualTest {

    @Value("${authorization.config.security.location:http://localhost:9002/auth}")
    private String baseUrl;

    public static void main(String[] args) {
        System.setProperty("spring.profiles.active", "manual-test");
        SpringApplication.run(EmailNotificationManualTest.class, args);
    }

    @Bean
    public CommandLineRunner commandLineRunner(
            EmailNotificationService emailNotificationService,
            RabbitTemplate rabbitTemplate,
            ObjectMapper objectMapper) {

        return args -> {
            Scanner scanner = new Scanner(System.in);
            boolean continueRunning = true;

            printBanner();

            while (continueRunning) {
                printMenu();
                String choice = scanner.nextLine().trim();

                try {
                    switch (choice) {
                        case "1":
                            sendVerificationEmail(emailNotificationService, scanner);
                            break;
                        case "2":
                            sendWelcomeEmail(emailNotificationService, scanner);
                            break;
                        case "3":
                            sendBothEmails(emailNotificationService, scanner);
                            break;
                        case "4":
                            sendBulkEmails(emailNotificationService, scanner);
                            break;
                        case "5":
                            checkRabbitMQConnection(rabbitTemplate);
                            break;
                        case "6":
                            continueRunning = false;
                            System.out.println("👋 Goodbye!");
                            break;
                        default:
                            System.out.println("❌ Invalid option. Please try again.");
                    }
                } catch (Exception e) {
                    System.err.println("❌ Error: " + e.getMessage());
                    e.printStackTrace();
                }

                if (continueRunning && !choice.equals("5")) {
                    System.out.println("\nPress Enter to continue...");
                    scanner.nextLine();
                }
            }

            scanner.close();
            System.exit(0);
        };
    }

    private void printBanner() {
        System.out.println("╔════════════════════════════════════════════════════════════════╗");
        System.out.println("║            EMAIL NOTIFICATION SERVICE TEST RUNNER             ║");
        System.out.println("║                                                                ║");
        System.out.println("║  This tool sends real emails through the communications       ║");
        System.out.println("║  service. Make sure RabbitMQ and the communications service   ║");
        System.out.println("║  are running before proceeding.                              ║");
        System.out.println("╚════════════════════════════════════════════════════════════════╝");
        System.out.println();
    }

    private void printMenu() {
        System.out.println("\n┌─────────────────────────────────────────┐");
        System.out.println("│            MAIN MENU                    │");
        System.out.println("├─────────────────────────────────────────┤");
        System.out.println("│ 1. Send Verification Email              │");
        System.out.println("│ 2. Send Welcome Email                   │");
        System.out.println("│ 3. Send Both Emails (Verification+Welcome)│");
        System.out.println("│ 4. Send Bulk Test Emails               │");
        System.out.println("│ 5. Check RabbitMQ Connection           │");
        System.out.println("│ 6. Exit                                │");
        System.out.println("└─────────────────────────────────────────┘");
        System.out.print("Enter your choice: ");
    }

    private void sendVerificationEmail(EmailNotificationService service, Scanner scanner) {
        System.out.println("\n📧 SEND VERIFICATION EMAIL");
        System.out.println("─────────────────────────");

        User user = getUserInput(scanner);
        String token = UUID.randomUUID().toString();

        System.out.println("\n📤 Sending verification email...");
        System.out.println("Token: " + token);
        System.out.println("Verification URL: " + baseUrl + "/verify-email?token=" + token);

        service.sendEmailVerification(user, token);

        System.out.println("✅ Verification email sent successfully!");
        System.out.println("Check the inbox for: " + user.getEmail());
    }

    private void sendWelcomeEmail(EmailNotificationService service, Scanner scanner) {
        System.out.println("\n📧 SEND WELCOME EMAIL");
        System.out.println("────────────────────");

        User user = getUserInput(scanner);
        user.setIsEmailVerified(true);

        System.out.println("\n📤 Sending welcome email...");
        System.out.println("Login URL: " + baseUrl + "/login");

        service.sendWelcomeEmail(user);

        System.out.println("✅ Welcome email sent successfully!");
        System.out.println("Check the inbox for: " + user.getEmail());
    }

    private void sendBothEmails(EmailNotificationService service, Scanner scanner) {
        System.out.println("\n📧 SEND BOTH EMAILS");
        System.out.println("──────────────────");

        User user = getUserInput(scanner);
        String token = UUID.randomUUID().toString();

        System.out.println("\n📤 Sending verification email...");
        service.sendEmailVerification(user, token);
        System.out.println("✅ Verification email sent!");

        try {
            Thread.sleep(2000);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }

        user.setIsEmailVerified(true);
        System.out.println("\n📤 Sending welcome email...");
        service.sendWelcomeEmail(user);
        System.out.println("✅ Welcome email sent!");

        System.out.println("\n✅ Both emails sent successfully!");
        System.out.println("Check the inbox for 2 emails at: " + user.getEmail());
    }

    private void sendBulkEmails(EmailNotificationService service, Scanner scanner) {
        System.out.println("\n📧 SEND BULK TEST EMAILS");
        System.out.println("───────────────────────");

        System.out.print("Enter base email address (e.g., test@example.com): ");
        String baseEmail = scanner.nextLine().trim();

        System.out.print("Enter number of emails to send: ");
        int count = Integer.parseInt(scanner.nextLine().trim());

        System.out.print("Enter delay between emails in milliseconds (0 for no delay): ");
        int delay = Integer.parseInt(scanner.nextLine().trim());

        System.out.println("\n📤 Sending " + count + " emails...");

        long startTime = System.currentTimeMillis();

        for (int i = 1; i <= count; i++) {
            String email = baseEmail.replace("@", "+test" + i + "@");
            User user = User.builder()
                    .id(UUID.randomUUID().toString())
                    .tenantId("bulk-test-tenant")
                    .username("bulktest_" + i)
                    .email(email)
                    .firstName("Test")
                    .lastName("User " + i)
                    .isActive(true)
                    .isEmailVerified(false)
                    .createdAt(OffsetDateTime.now())
                    .build();

            String token = UUID.randomUUID().toString();

            try {
                service.sendEmailVerification(user, token);
                System.out.println("  ✅ Email " + i + "/" + count + " sent to: " + email);

                if (delay > 0 && i < count) {
                    Thread.sleep(delay);
                }
            } catch (Exception e) {
                System.err.println("  ❌ Failed to send email " + i + ": " + e.getMessage());
            }
        }

        long endTime = System.currentTimeMillis();
        long duration = endTime - startTime;

        System.out.println("\n📊 Bulk Email Statistics:");
        System.out.println("  • Total emails sent: " + count);
        System.out.println("  • Total time: " + duration + "ms");
        System.out.println("  • Average time per email: " + (duration / count) + "ms");
    }

    private void checkRabbitMQConnection(RabbitTemplate rabbitTemplate) {
        System.out.println("\n🔌 CHECKING RABBITMQ CONNECTION");
        System.out.println("────────────────────────────────");

        try {
            rabbitTemplate.execute(channel -> {
                System.out.println("✅ Successfully connected to RabbitMQ!");
                System.out.println("  • Open: " + channel.isOpen());
                System.out.println("  • Channel Number: " + channel.getChannelNumber());
                System.out.println("  • Connection: " + channel.getConnection().getAddress());
                return null;
            });
        } catch (Exception e) {
            System.err.println("❌ Failed to connect to RabbitMQ: " + e.getMessage());
        }
    }

    private User getUserInput(Scanner scanner) {
        System.out.print("Enter email address (or press Enter for default: adebola@factorialsystems.io): ");
        String email = scanner.nextLine().trim();
        if (email.isEmpty()) {
            email = "adebola@factorialsystems.io";
        }

        System.out.print("Enter first name (or press Enter for 'Test'): ");
        String firstName = scanner.nextLine().trim();
        if (firstName.isEmpty()) {
            firstName = "Test";
        }

        System.out.print("Enter last name (or press Enter for 'User'): ");
        String lastName = scanner.nextLine().trim();
        if (lastName.isEmpty()) {
            lastName = "User";
        }

        return User.builder()
                .id(UUID.randomUUID().toString())
                .tenantId("manual-test-tenant-" + UUID.randomUUID().toString())
                .username("manual_test_" + System.currentTimeMillis())
                .email(email)
                .firstName(firstName)
                .lastName(lastName)
                .isActive(true)
                .isEmailVerified(false)
                .createdAt(OffsetDateTime.now())
                .updatedAt(OffsetDateTime.now())
                .build();
    }
}
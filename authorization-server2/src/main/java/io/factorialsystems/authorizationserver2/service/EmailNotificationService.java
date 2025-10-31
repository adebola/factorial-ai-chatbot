package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.dto.EmailNotificationRequest;
import io.factorialsystems.authorizationserver2.model.User;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.util.HashMap;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class EmailNotificationService {

    private final RabbitTemplate rabbitTemplate;
    private final ObjectMapper objectMapper;

    @Value("${authorization.config.rabbitmq.exchange.name:topic-exchange}")
    private String exchangeName;

    @Value("${authorization.config.rabbitmq.key.email-notification:email.notification}")
    private String emailRoutingKey;

    @Value("${authorization.config.security.location:http://localhost:9002/auth}")
    private String baseUrl;

    /**
     * Send email verification notification
     */
    public void sendEmailVerification(User user, String verificationToken) {
        try {
            String verificationUrl = baseUrl + "/verify-email?token=" + verificationToken;

            Map<String, Object> templateData = new HashMap<>();
            templateData.put("firstName", user.getFirstName());
            templateData.put("lastName", user.getLastName());
            templateData.put("email", user.getEmail());
            templateData.put("verificationUrl", verificationUrl);
            templateData.put("baseUrl", baseUrl);

            String subject = "Verify Your Email Address - ChatCraft";
            String htmlContent = generateEmailVerificationHtml(templateData);
            String textContent = generateEmailVerificationText(templateData);

            EmailNotificationRequest request = EmailNotificationRequest.builder()
                .tenantId(user.getTenantId()) // System tenant for authorization emails
                .toEmail(user.getEmail())
                .toName(user.getFirstName() + " " + user.getLastName())
                .subject(subject)
                .htmlContent(htmlContent)
                .textContent(textContent)
                .template(EmailNotificationRequest.EmailTemplate.builder()
                    .templateName("email_verification")
                    .type(EmailNotificationRequest.EmailTemplate.TemplateType.EMAIL_VERIFICATION)
                    .build())
                .templateData(templateData)
                .build();

            publishEmailNotification(request);

            log.info("Sent email verification notification for user: {} ({})", user.getId(), user.getEmail());

        } catch (Exception e) {
            log.error("Failed to send email verification for user: {} ({})", user.getId(), user.getEmail(), e);
            throw new RuntimeException("Failed to send verification email", e);
        }
    }

    /**
     * Send a welcome email after successful verification
     */
    public void sendWelcomeEmail(User user) {
        try {
            Map<String, Object> templateData = new HashMap<>();
            templateData.put("firstName", user.getFirstName());
            templateData.put("lastName", user.getLastName());
            templateData.put("email", user.getEmail());
            templateData.put("loginUrl", baseUrl + "/login");
            templateData.put("baseUrl", baseUrl);

            String subject = "Welcome to ChatCraft!";
            String htmlContent = generateWelcomeEmailHtml(templateData);
            String textContent = generateWelcomeEmailText(templateData);

            EmailNotificationRequest request = EmailNotificationRequest.builder()
                .tenantId(user.getTenantId())
                .toEmail(user.getEmail())
                .toName(user.getFirstName() + " " + user.getLastName())
                .subject(subject)
                .htmlContent(htmlContent)
                .textContent(textContent)
                .template(EmailNotificationRequest.EmailTemplate.builder()
                    .templateName("welcome")
                    .type(EmailNotificationRequest.EmailTemplate.TemplateType.WELCOME)
                    .build())
                .templateData(templateData)
                .build();

            publishEmailNotification(request);

            log.info("Sent welcome email for user: {} ({})", user.getId(), user.getEmail());

        } catch (Exception e) {
            log.error("Failed to send welcome email for user: {} ({})", user.getId(), user.getEmail(), e);
            // Don't throw exception for welcome email failures as it's not critical
        }
    }

    /**
     * Publish email notification to RabbitMQ
     */
    private void publishEmailNotification(EmailNotificationRequest request) {
        try {
            String message = objectMapper.writeValueAsString(request);

            rabbitTemplate.convertAndSend(exchangeName, emailRoutingKey, message);

            log.debug("Published email notification to queue: exchange={}, routingKey={}, recipient={}",
                exchangeName, emailRoutingKey, request.getToEmail());

        } catch (JsonProcessingException e) {
            log.error("Failed to serialize email notification request", e);
            throw new RuntimeException("Failed to serialize email notification", e);
        } catch (Exception e) {
            log.error("Failed to publish email notification to queue", e);
            throw new RuntimeException("Failed to publish email notification", e);
        }
    }

    /**
     * Generate HTML content for email verification
     */
    private String generateEmailVerificationHtml(Map<String, Object> data) {
        return """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Verify Your Email</title>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { text-align: center; margin-bottom: 30px; }
                    .logo { max-width: 200px; height: auto; }
                    .content { background: #f9f9f9; padding: 30px; border-radius: 8px; margin: 20px 0; }
                    .button { display: inline-block; background: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }
                    .footer { text-align: center; color: #666; font-size: 14px; margin-top: 30px; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>ChatCraft</h1>
                </div>
                <div class="content">
                    <h2>Verify Your Email Address</h2>
                    <p>Hello %s,</p>
                    <p>Thank you for registering with ChatCraft! To complete your registration, please verify your email address by clicking the button below:</p>
                    <p style="text-align: center;">
                        <a href="%s" class="button">Verify Email Address</a>
                    </p>
                    <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                    <p style="word-break: break-all; color: #666;">%s</p>
                    <p><strong>This verification link will expire in 24 hours.</strong></p>
                    <p>If you didn't create an account with ChatCraft, you can safely ignore this email.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2024 ChatCraft. All rights reserved.</p>
                </div>
            </body>
            </html>
            """.formatted(
                data.get("firstName"),
                data.get("verificationUrl"),
                data.get("verificationUrl")
            );
    }

    /**
     * Generate plain text content for email verification
     */
    private String generateEmailVerificationText(Map<String, Object> data) {
        return """
            ChatCraft - Verify Your Email Address

            Hello %s,

            Thank you for registering with ChatCraft! To complete your registration, please verify your email address by visiting this link:

            %s

            This verification link will expire in 24 hours.

            If you didn't create an account with ChatCraft, you can safely ignore this email.

            Best regards,
            The ChatCraft Team
            """.formatted(
                data.get("firstName"),
                data.get("verificationUrl")
            );
    }

    /**
     * Generate HTML content for welcome email
     */
    private String generateWelcomeEmailHtml(Map<String, Object> data) {
        return """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Welcome to ChatCraft</title>
                <style>
                    body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }
                    .header { text-align: center; margin-bottom: 30px; }
                    .content { background: #f9f9f9; padding: 30px; border-radius: 8px; margin: 20px 0; }
                    .button { display: inline-block; background: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }
                    .footer { text-align: center; color: #666; font-size: 14px; margin-top: 30px; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>ChatCraft</h1>
                </div>
                <div class="content">
                    <h2>Welcome to ChatCraft!</h2>
                    <p>Hello %s,</p>
                    <p>Congratulations! Your email has been verified and your account is now active.</p>
                    <p>You can now sign in to your ChatCraft account and start building AI-powered chat experiences.</p>
                    <p style="text-align: center;">
                        <a href="%s" class="button">Sign In to ChatCraft</a>
                    </p>
                    <p>If you have any questions or need help getting started, feel free to contact our support team.</p>
                </div>
                <div class="footer">
                    <p>&copy; 2024 ChatCraft. All rights reserved.</p>
                </div>
            </body>
            </html>
            """.formatted(
                data.get("firstName"),
                data.get("loginUrl")
            );
    }

    /**
     * Generate plain text content for welcome email
     */
    private String generateWelcomeEmailText(Map<String, Object> data) {
        return """
            ChatCraft - Welcome!

            Hello %s,

            Congratulations! Your email has been verified and your account is now active.

            You can now sign in to your ChatCraft account and start building AI-powered chat experiences.

            Sign in here: %s

            If you have any questions or need help getting started, feel free to contact our support team.

            Best regards,
            The ChatCraft Team
            """.formatted(
                data.get("firstName"),
                data.get("loginUrl")
            );
    }
}
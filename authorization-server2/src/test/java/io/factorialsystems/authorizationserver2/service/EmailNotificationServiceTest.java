package io.factorialsystems.authorizationserver2.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.factorialsystems.authorizationserver2.dto.EmailNotificationRequest;
import io.factorialsystems.authorizationserver2.model.User;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.OffsetDateTime;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class EmailNotificationServiceTest {

    @Mock
    private RabbitTemplate rabbitTemplate;

    @Mock
    private ObjectMapper objectMapper;

    @InjectMocks
    private EmailNotificationService emailNotificationService;

    private User testUser;
    private final String exchangeName = "topic-exchange";
    private final String emailRoutingKey = "email.notification";
    private final String baseUrl = "http://localhost:9002/auth";

    @BeforeEach
    void setUp() {
        // Set up test user
        testUser = User.builder()
                .id("6cae42d3-29ba-4a79-8549-a4fc7ed324da")
                .tenantId("9eb23c01-b66a-4e23-8316-4884532d5b04")
                .username("adebola")
                .email("adebola@factorialsystems.io")
                .firstName("Adebola")
                .lastName("Omoboya")
                .isActive(false)
                .isEmailVerified(false)
                .createdAt(OffsetDateTime.now())
                .build();

        // Inject field values using ReflectionTestUtils
        ReflectionTestUtils.setField(emailNotificationService, "exchangeName", exchangeName);
        ReflectionTestUtils.setField(emailNotificationService, "emailRoutingKey", emailRoutingKey);
        ReflectionTestUtils.setField(emailNotificationService, "baseUrl", baseUrl);
    }

    @Test
    void sendEmailVerification() throws Exception {
        // Given
        String verificationToken = "test-verification-token-123";
        String expectedVerificationUrl = baseUrl + "/verify-email?token=" + verificationToken;
        String expectedJsonMessage = "{\"email\":\"test@example.com\"}";

        when(objectMapper.writeValueAsString(any(EmailNotificationRequest.class)))
                .thenReturn(expectedJsonMessage);

        // When
        emailNotificationService.sendEmailVerification(testUser, verificationToken);

        // Then
        // Verify ObjectMapper was called to serialize the request
        ArgumentCaptor<EmailNotificationRequest> requestCaptor =
                ArgumentCaptor.forClass(EmailNotificationRequest.class);
        verify(objectMapper).writeValueAsString(requestCaptor.capture());

        EmailNotificationRequest capturedRequest = requestCaptor.getValue();
        assertNotNull(capturedRequest);
        assertEquals(testUser.getTenantId(), capturedRequest.getTenantId());
        assertEquals(testUser.getEmail(), capturedRequest.getToEmail());
        assertEquals("Adebola Omoboya", capturedRequest.getToName());
        assertEquals("Verify Your Email Address - ChatCraft", capturedRequest.getSubject());
        assertNotNull(capturedRequest.getHtmlContent());
        assertNotNull(capturedRequest.getTextContent());
        assertTrue(capturedRequest.getHtmlContent().contains(expectedVerificationUrl));
        assertTrue(capturedRequest.getTextContent().contains(expectedVerificationUrl));
        assertTrue(capturedRequest.getHtmlContent().contains("Adebola"));

        // Verify template information
        assertNotNull(capturedRequest.getTemplate());
        assertEquals("email_verification", capturedRequest.getTemplate().getTemplateName());
        assertEquals(EmailNotificationRequest.EmailTemplate.TemplateType.EMAIL_VERIFICATION,
                capturedRequest.getTemplate().getType());

        // Verify template data
        assertNotNull(capturedRequest.getTemplateData());
        assertEquals("Adebola", capturedRequest.getTemplateData().get("firstName"));
        assertEquals("Omoboya", capturedRequest.getTemplateData().get("lastName"));
        assertEquals("adebola@factorialsystems.io", capturedRequest.getTemplateData().get("email"));
        assertEquals(expectedVerificationUrl, capturedRequest.getTemplateData().get("verificationUrl"));
        assertEquals(baseUrl, capturedRequest.getTemplateData().get("baseUrl"));

        // Verify RabbitTemplate was called with correct parameters
        verify(rabbitTemplate).convertAndSend(
                eq(exchangeName),
                eq(emailRoutingKey),
                eq(expectedJsonMessage)
        );
    }

    @Test
    void sendEmailVerification_throwsExceptionOnSerializationFailure() throws Exception {
        // Given
        String verificationToken = "test-token";
        when(objectMapper.writeValueAsString(any(EmailNotificationRequest.class)))
                .thenThrow(new com.fasterxml.jackson.core.JsonProcessingException("Serialization error") {});

        // When & Then
        RuntimeException exception = assertThrows(RuntimeException.class, () ->
                emailNotificationService.sendEmailVerification(testUser, verificationToken)
        );

        assertEquals("Failed to send verification email", exception.getMessage());
        assertNotNull(exception.getCause());

        // Verify RabbitTemplate was not called
        verify(rabbitTemplate, never()).convertAndSend(anyString(), anyString(), anyString());
    }

    @Test
    void sendEmailVerification_throwsExceptionOnRabbitMQFailure() throws Exception {
        // Given
        String verificationToken = "test-token";
        String expectedJsonMessage = "{\"email\":\"test@example.com\"}";

        when(objectMapper.writeValueAsString(any(EmailNotificationRequest.class)))
                .thenReturn(expectedJsonMessage);
        doThrow(new RuntimeException("RabbitMQ connection failed"))
                .when(rabbitTemplate).convertAndSend(anyString(), anyString(), anyString());

        // When & Then
        RuntimeException exception = assertThrows(RuntimeException.class, () ->
                emailNotificationService.sendEmailVerification(testUser, verificationToken)
        );

        assertEquals("Failed to send verification email", exception.getMessage());
        assertNotNull(exception.getCause());
    }

    @Test
    void sendWelcomeEmail() throws Exception {
        // Given
        String expectedLoginUrl = baseUrl + "/login";
        String expectedJsonMessage = "{\"email\":\"test@example.com\"}";

        when(objectMapper.writeValueAsString(any(EmailNotificationRequest.class)))
                .thenReturn(expectedJsonMessage);

        // When
        emailNotificationService.sendWelcomeEmail(testUser);

        // Then
        // Verify ObjectMapper was called to serialize the request
        ArgumentCaptor<EmailNotificationRequest> requestCaptor =
                ArgumentCaptor.forClass(EmailNotificationRequest.class);
        verify(objectMapper).writeValueAsString(requestCaptor.capture());

        EmailNotificationRequest capturedRequest = requestCaptor.getValue();
        assertNotNull(capturedRequest);
        assertEquals(testUser.getTenantId(), capturedRequest.getTenantId());
        assertEquals(testUser.getEmail(), capturedRequest.getToEmail());
        assertEquals("Adebola Omoboya", capturedRequest.getToName());
        assertEquals("Welcome to ChatCraft!", capturedRequest.getSubject());
        assertNotNull(capturedRequest.getHtmlContent());
        assertNotNull(capturedRequest.getTextContent());
        assertTrue(capturedRequest.getHtmlContent().contains(expectedLoginUrl));
        assertTrue(capturedRequest.getTextContent().contains(expectedLoginUrl));
        assertTrue(capturedRequest.getHtmlContent().contains("Adebola"));
        assertTrue(capturedRequest.getHtmlContent().contains("Your email has been verified"));

        // Verify template information
        assertNotNull(capturedRequest.getTemplate());
        assertEquals("welcome", capturedRequest.getTemplate().getTemplateName());
        assertEquals(EmailNotificationRequest.EmailTemplate.TemplateType.WELCOME,
                capturedRequest.getTemplate().getType());

        // Verify template data
        assertNotNull(capturedRequest.getTemplateData());
        assertEquals("Adebola", capturedRequest.getTemplateData().get("firstName"));
        assertEquals("Omoboya", capturedRequest.getTemplateData().get("lastName"));
        assertEquals("adebola@factorialsystems.io", capturedRequest.getTemplateData().get("email"));
        assertEquals(expectedLoginUrl, capturedRequest.getTemplateData().get("loginUrl"));
        assertEquals(baseUrl, capturedRequest.getTemplateData().get("baseUrl"));

        // Verify RabbitTemplate was called with correct parameters
        verify(rabbitTemplate).convertAndSend(
                eq(exchangeName),
                eq(emailRoutingKey),
                eq(expectedJsonMessage)
        );
    }

    @Test
    void sendWelcomeEmail_doesNotThrowExceptionOnFailure() throws Exception {
        // Given
        when(objectMapper.writeValueAsString(any(EmailNotificationRequest.class)))
                .thenThrow(new com.fasterxml.jackson.core.JsonProcessingException("Serialization error") {});

        // When - should not throw exception
        assertDoesNotThrow(() -> emailNotificationService.sendWelcomeEmail(testUser));

        // Then
        // Verify RabbitTemplate was not called
        verify(rabbitTemplate, never()).convertAndSend(anyString(), anyString(), anyString());
    }

    @Test
    void sendWelcomeEmail_handlesRabbitMQFailureGracefully() throws Exception {
        // Given
        String expectedJsonMessage = "{\"email\":\"test@example.com\"}";

        when(objectMapper.writeValueAsString(any(EmailNotificationRequest.class)))
                .thenReturn(expectedJsonMessage);
        doThrow(new RuntimeException("RabbitMQ connection failed"))
                .when(rabbitTemplate).convertAndSend(anyString(), anyString(), anyString());

        // When - should not throw exception (welcome email failures are not critical)
        assertDoesNotThrow(() -> emailNotificationService.sendWelcomeEmail(testUser));

        // Then
        verify(rabbitTemplate).convertAndSend(
                eq(exchangeName),
                eq(emailRoutingKey),
                eq(expectedJsonMessage)
        );
    }
}
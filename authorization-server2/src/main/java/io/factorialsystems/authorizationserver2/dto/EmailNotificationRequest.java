package io.factorialsystems.authorizationserver2.dto;

import lombok.*;

import java.util.Map;

@Getter
@Setter
@ToString
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class EmailNotificationRequest {

    private String tenantId;
    private String toEmail;
    private String toName;
    private String subject;
    private String htmlContent;
    private String textContent;
    private EmailTemplate template;
    private Map<String, Object> templateData;

    @Getter
    @Setter
    @ToString
    @NoArgsConstructor
    @AllArgsConstructor
    @Builder
    public static class EmailTemplate {
        private String templateId;
        private String templateName;
        private TemplateType type;

        public enum TemplateType {
            EMAIL_VERIFICATION,
            PASSWORD_RESET,
            WELCOME,
            INVITATION
        }
    }
}
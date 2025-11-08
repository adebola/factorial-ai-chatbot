package io.factorialsystems.authorizationserver2.dto;

import lombok.*;
import jakarta.validation.constraints.*;

import java.util.List;

@Getter
@Setter
@ToString
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class TenantRegistrationRequest {
    
    // Organization Information
    @NotBlank(message = "Organization name is required")
    @Size(min = 2, max = 100, message = "Organization name must be between 2 and 100 characters")
    private String name;

    // Domain is now optional - not required for registration
    @Pattern(regexp = "^[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", message = "Please enter a valid domain (e.g., yourcompany.com)")
    private String domain;
    
    
    // Administrator Account Information
    @NotBlank(message = "Administrator username is required")
    @Size(min = 3, max = 50, message = "Username must be between 3 and 50 characters")
    @Pattern(regexp = "^[a-zA-Z0-9_-]+$", message = "Username can only contain letters, numbers, underscores, and hyphens")
    private String adminUsername;
    
    @NotBlank(message = "Administrator email is required")
    @Email(message = "Please enter a valid email address")
    private String adminEmail;
    
    @Size(min = 1, max = 50, message = "First name must be between 1 and 50 characters")
    private String adminFirstName;
    
    @Size(min = 1, max = 50, message = "Last name must be between 1 and 50 characters")
    private String adminLastName;
    
    @NotBlank(message = "Administrator password is required")
    @Size(min = 8, max = 128, message = "Password must be at least 8 characters long")
    private String adminPassword;
    
    // Validation helper methods
    public boolean hasAdminPassword() {
        return adminPassword != null && !adminPassword.trim().isEmpty();
    }
    
    public String getFullAdminName() {
        StringBuilder fullName = new StringBuilder();
        if (adminFirstName != null && !adminFirstName.trim().isEmpty()) {
            fullName.append(adminFirstName.trim());
        }
        if (adminLastName != null && !adminLastName.trim().isEmpty()) {
            if (fullName.length() > 0) {
                fullName.append(" ");
            }
            fullName.append(adminLastName.trim());
        }
        return fullName.toString();
    }
    
    public String getDomainNormalized() {
        return domain != null ? domain.toLowerCase().trim() : null;
    }
}
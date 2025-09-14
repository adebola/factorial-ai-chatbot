package io.factorialsystems.authorizationserver.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

import java.util.List;

/**
 * DTO for tenant creation requests
 */
@Getter
@Setter
@ToString
public class TenantCreateRequest {
    
    @NotBlank(message = "Tenant name is required")
    @Size(max = 255, message = "Tenant name must not exceed 255 characters")
    private String name;
    
    @NotBlank(message = "Domain is required")
    @Size(max = 255, message = "Domain must not exceed 255 characters")
    @Pattern(regexp = "^[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$", message = "Domain must be a valid domain name (e.g., example.com)")
    private String domain;
    
    @Size(max = 1000, message = "Callback URLs must not exceed 1000 characters")
    private List<String> callbackUrls;
    
    private List<String> allowedScopes;
    
    private String planId;
    
    // Admin user details (for the first user in the tenant)
    @NotBlank(message = "Admin username is required")
    @Size(max = 255, message = "Admin username must not exceed 255 characters")
    @Pattern(regexp = "^[a-zA-Z0-9._-]+$", message = "Username must contain only letters, numbers, dots, underscores, and hyphens")
    private String adminUsername;
    
    @NotBlank(message = "Admin email is required")
    @Email(message = "Invalid email format")
    @Size(max = 255, message = "Admin email must not exceed 255 characters")
    private String adminEmail;
    
    @Size(max = 255, message = "Admin first name must not exceed 255 characters")
    private String adminFirstName;
    
    @Size(max = 255, message = "Admin last name must not exceed 255 characters")
    private String adminLastName;
    
    // Password is optional - if not provided, user will be invited via email
    @Size(min = 8, max = 128, message = "Password must be between 8 and 128 characters")
    private String adminPassword;
}
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
 * DTO for user invitation requests
 */
@Getter
@Setter
@ToString
public class InvitationRequest {
    
    @NotBlank(message = "Username is required")
    @Size(max = 255, message = "Username must not exceed 255 characters")
    @Pattern(regexp = "^[a-zA-Z0-9._-]+$", message = "Username must contain only letters, numbers, dots, underscores, and hyphens")
    private String username;
    
    @NotBlank(message = "Email is required")
    @Email(message = "Invalid email format")
    @Size(max = 255, message = "Email must not exceed 255 characters")
    private String email;
    
    @Size(max = 255, message = "First name must not exceed 255 characters")
    private String firstName;
    
    @Size(max = 255, message = "Last name must not exceed 255 characters")
    private String lastName;
    
    /**
     * Role IDs to assign to the invited user
     * If empty, default roles will be assigned
     */
    private List<String> roleIds;
    
    /**
     * Whether the invited user should be a tenant admin
     */
    private Boolean isTenantAdmin = false;
    
    /**
     * Custom message to include in the invitation email
     */
    @Size(max = 1000, message = "Message must not exceed 1000 characters")
    private String message;
    
    /**
     * Number of days the invitation should be valid (default: 7 days)
     */
    private Integer validityDays = 7;
}
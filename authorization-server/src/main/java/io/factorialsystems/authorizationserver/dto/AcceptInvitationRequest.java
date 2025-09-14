package io.factorialsystems.authorizationserver.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;

/**
 * DTO for accepting invitation requests
 */
@Getter
@Setter
@ToString
public class AcceptInvitationRequest {
    
    @NotBlank(message = "Invitation token is required")
    private String invitationToken;
    
    @NotBlank(message = "Password is required")
    @Size(min = 8, max = 128, message = "Password must be between 8 and 128 characters")
    private String password;
    
    @NotBlank(message = "Password confirmation is required")
    private String passwordConfirmation;
    
    @Size(max = 255, message = "First name must not exceed 255 characters")
    private String firstName;
    
    @Size(max = 255, message = "Last name must not exceed 255 characters")  
    private String lastName;
    
    /**
     * Validate that password and confirmation match
     */
    public boolean isPasswordValid() {
        return password != null && password.equals(passwordConfirmation);
    }
}
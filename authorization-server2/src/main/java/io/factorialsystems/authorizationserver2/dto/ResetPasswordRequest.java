package io.factorialsystems.authorizationserver2.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Request DTO for password reset functionality
 * Contains the reset token, new password, and password confirmation
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class ResetPasswordRequest {

    @NotBlank(message = "Reset token is required")
    private String token;

    @NotBlank(message = "New password is required")
    @Size(min = 8, message = "Password must be at least 8 characters long")
    private String newPassword;

    @NotBlank(message = "Password confirmation is required")
    private String confirmPassword;
}

package io.factorialsystems.authorizationserver2.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Request DTO for forgot password functionality
 * Contains the email address where password reset link will be sent
 */
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class ForgotPasswordRequest {

    @Email(message = "Please provide a valid email address")
    @NotBlank(message = "Email is required")
    private String email;
}

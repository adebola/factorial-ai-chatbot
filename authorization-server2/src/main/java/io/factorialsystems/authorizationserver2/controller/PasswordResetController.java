package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.dto.ForgotPasswordRequest;
import io.factorialsystems.authorizationserver2.dto.ResetPasswordRequest;
import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.model.VerificationToken;
import io.factorialsystems.authorizationserver2.service.EmailNotificationService;
import io.factorialsystems.authorizationserver2.service.UserService;
import io.factorialsystems.authorizationserver2.service.VerificationService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Slf4j
@Controller
@RequiredArgsConstructor
public class PasswordResetController {

    private final UserService userService;
    private final VerificationService verificationService;
    private final EmailNotificationService emailNotificationService;

    @Value("${authorization.config.security.location:http://localhost:9002/auth}")
    private String baseUrl;

    /**
     * Display forgot password form
     */
    @GetMapping("/forgot-password")
    public String showForgotPasswordPage(Model model) {
        model.addAttribute("forgotPasswordRequest", new ForgotPasswordRequest());
        return "forgot-password";
    }

    /**
     * Process forgot password request - send reset email
     */
    @PostMapping("/forgot-password")
    public String processForgotPassword(
            @Valid @ModelAttribute("forgotPasswordRequest") ForgotPasswordRequest request,
            BindingResult bindingResult,
            Model model,
            RedirectAttributes redirectAttributes) {

        // Handle validation errors
        if (bindingResult.hasErrors()) {
            return "forgot-password";
        }

        try {
            String email = request.getEmail().toLowerCase().trim();

            // Check if user exists (but don't reveal this to prevent user enumeration)
            User user = userService.findByEmail(email);

            if (user != null) {
                // Generate password reset token
                VerificationToken token = verificationService.createPasswordResetToken(user.getId(), email);

                // Generate reset URL
                String resetUrl = verificationService.generatePasswordResetUrl(token.getToken());

                // Send password reset email
                String userName = user.getFirstName() != null ? user.getFirstName() : user.getUsername();
                emailNotificationService.sendPasswordResetEmail(email, userName, token.getToken(), baseUrl);

                log.info("Password reset email sent to: {}", email);
            } else {
                // User doesn't exist, but don't reveal this for security
                log.warn("Password reset requested for non-existent email: {}", email);
            }

            // Always show success message (security: no user enumeration)
            redirectAttributes.addFlashAttribute("successMessage",
                    "If an account exists with that email, you will receive password reset instructions.");
            return "redirect:/forgot-password";

        } catch (IllegalStateException e) {
            // Rate limiting error
            log.warn("Password reset rate limit exceeded for email: {}", request.getEmail());
            model.addAttribute("errorMessage", e.getMessage());
            return "forgot-password";
        } catch (Exception e) {
            log.error("Error processing forgot password request", e);
            model.addAttribute("errorMessage", "An error occurred. Please try again later.");
            return "forgot-password";
        }
    }

    /**
     * Display reset password form (after clicking email link)
     */
    @GetMapping("/reset-password")
    public String showResetPasswordPage(
            @RequestParam("token") String token,
            Model model,
            RedirectAttributes redirectAttributes) {

        try {
            // Validate token
            VerificationService.VerificationResult result = verificationService.validatePasswordResetToken(token);

            if (!result.isSuccess()) {
                // Token is invalid, expired, or already used
                log.warn("Invalid password reset token: {}", token);
                redirectAttributes.addFlashAttribute("errorMessage", result.getMessage());
                return "redirect:/login";
            }

            // Token is valid - show reset form
            ResetPasswordRequest resetRequest = new ResetPasswordRequest();
            resetRequest.setToken(token);
            model.addAttribute("resetPasswordRequest", resetRequest);
            model.addAttribute("token", token);

            return "reset-password";

        } catch (Exception e) {
            log.error("Error validating password reset token", e);
            redirectAttributes.addFlashAttribute("errorMessage", "An error occurred. Please try again.");
            return "redirect:/login";
        }
    }

    /**
     * Process password reset - update password
     */
    @PostMapping("/reset-password")
    public String processResetPassword(
            @Valid @ModelAttribute("resetPasswordRequest") ResetPasswordRequest request,
            BindingResult bindingResult,
            Model model,
            RedirectAttributes redirectAttributes) {

        // Handle validation errors
        if (bindingResult.hasErrors()) {
            model.addAttribute("token", request.getToken());
            return "reset-password";
        }

        try {
            // Check passwords match
            if (!request.getNewPassword().equals(request.getConfirmPassword())) {
                model.addAttribute("errorMessage", "Passwords do not match");
                model.addAttribute("token", request.getToken());
                return "reset-password";
            }

            // Validate token again
            VerificationService.VerificationResult result =
                    verificationService.validatePasswordResetToken(request.getToken());

            if (!result.isSuccess()) {
                redirectAttributes.addFlashAttribute("errorMessage", result.getMessage());
                return "redirect:/login";
            }

            // Get the verification token to extract email
            VerificationToken token = verificationService.getTokenByString(request.getToken());
            if (token == null) {
                redirectAttributes.addFlashAttribute("errorMessage", "Invalid reset link");
                return "redirect:/login";
            }

            // Reset the password
            userService.resetPassword(token.getEmail(), request.getNewPassword());

            // Mark token as used
            verificationService.markPasswordResetTokenAsUsed(request.getToken());

            log.info("Password reset successfully for email: {}", token.getEmail());

            // Redirect to login with success message
            redirectAttributes.addFlashAttribute("successMessage",
                    "Your password has been reset successfully. You can now sign in with your new password.");
            return "redirect:/login";

        } catch (Exception e) {
            log.error("Error resetting password", e);
            model.addAttribute("errorMessage", "An error occurred. Please try again.");
            model.addAttribute("token", request.getToken());
            return "reset-password";
        }
    }
}

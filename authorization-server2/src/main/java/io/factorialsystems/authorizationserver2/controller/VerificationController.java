package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.service.VerificationService;
import io.factorialsystems.authorizationserver2.service.UserService;
import io.factorialsystems.authorizationserver2.service.EmailNotificationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

@Slf4j
@Controller
@RequiredArgsConstructor
public class VerificationController {

    private final VerificationService verificationService;
    private final UserService userService;
    private final EmailNotificationService emailNotificationService;

    /**
     * Handle email verification
     * This route is authentication-free to allow users to verify their email
     */
    @GetMapping("/verify-email")
    public String verifyEmail(@RequestParam(value = "token", required = false) String token, Model model) {
        log.info("Processing email verification request with token: {}", token);

        // Always set default model attributes to prevent blank pages
        model.addAttribute("pageTitle", "Email Verification");

        // Validate token parameter
        if (token == null || token.trim().isEmpty()) {
            log.warn("Email verification attempted without token");
            model.addAttribute("success", false);
            model.addAttribute("message", "Invalid verification link. Please check your email for the correct verification link.");
            model.addAttribute("pageTitle", "Invalid Verification Link");
            return "verification/email-verification-result";
        }

        try {
            // Verify the token
            VerificationService.VerificationResult result = verificationService.verifyEmailToken(token);

            if (result.isSuccess() && result.getUserId() != null) {
                // Get the user
                User user = userService.findById(result.getUserId());
                if (user == null) {
                    log.error("User not found for verification token: {}", result.getUserId());
                    model.addAttribute("success", false);
                    model.addAttribute("message", "User account not found. The verification link may be invalid.");
                    model.addAttribute("pageTitle", "User Not Found");
                    return "verification/email-verification-result";
                }

                // Check if user is already verified
                if (user.getIsActive() && user.getIsEmailVerified()) {
                    log.info("User already verified: {}", user.getId());
                    model.addAttribute("success", true);
                    model.addAttribute("message", "Your email has already been verified. Your account is ready to use!");
                    model.addAttribute("pageTitle", "Already Verified");
                    return "verification/email-verification-result";
                }

                // Activate the user
                user.setIsActive(true);
                user.setIsEmailVerified(true);
                userService.updateUser(user);

                // Send welcome email (best effort, don't fail verification if it fails)
                boolean welcomeEmailSent = false;
                try {
                    emailNotificationService.sendWelcomeEmail(user);
                    welcomeEmailSent = true;
                    log.info("Welcome email sent to verified user: {} ({})", user.getId(), user.getEmail());
                } catch (Exception e) {
                    log.warn("Failed to send welcome email to user: {} ({})", user.getId(), user.getEmail(), e);
                    // Continue with successful verification even if welcome email fails
                }

                log.info("Successfully verified email and activated user: {} ({})", user.getId(), user.getEmail());

                model.addAttribute("success", true);
                String successMessage = result.getMessage() != null ? result.getMessage() :
                    "Your email has been successfully verified and your account is now active!";

                if (!welcomeEmailSent) {
                    successMessage += " (Note: Welcome email could not be sent, but your account is fully activated.)";
                }

                model.addAttribute("message", successMessage);
                model.addAttribute("pageTitle", "Email Verified Successfully");

                return "verification/email-verification-result";
            } else {
                log.warn("Email verification failed for token: {} - {}", token, result.getMessage());

                model.addAttribute("success", false);
                String errorMessage = result.getMessage() != null ? result.getMessage() :
                    "The verification link is invalid or has expired. Please try registering again.";
                model.addAttribute("message", errorMessage);
                model.addAttribute("pageTitle", "Verification Failed");

                return "verification/email-verification-result";
            }

        } catch (Exception e) {
            log.error("Unexpected error during email verification for token: {}", token, e);

            model.addAttribute("success", false);
            model.addAttribute("message", "An unexpected error occurred while verifying your email. Please try again later or contact our support team if the problem persists.");
            model.addAttribute("pageTitle", "Verification Error");

            return "verification/email-verification-result";
        }
    }

    /**
     * Display email verification status page
     * This can be used for users to check their verification status
     */
    @GetMapping("/verification-status")
    public String verificationStatus(Model model) {
        model.addAttribute("pageTitle", "Email Verification Status");
        return "verification/verification-status";
    }

    /**
     * Test endpoints for verification page states (for development/testing)
     * These endpoints demonstrate all possible verification result states
     */
    @GetMapping("/verify-email-test-success")
    public String testVerificationSuccess(Model model) {
        model.addAttribute("success", true);
        model.addAttribute("message", "Test: Your email has been successfully verified and your account is now active!");
        model.addAttribute("pageTitle", "Test - Email Verified Successfully");
        return "verification/email-verification-result";
    }

    @GetMapping("/verify-email-test-failure")
    public String testVerificationFailure(Model model) {
        model.addAttribute("success", false);
        model.addAttribute("message", "Test: The verification link is invalid or has expired. Please try registering again.");
        model.addAttribute("pageTitle", "Test - Verification Failed");
        return "verification/email-verification-result";
    }

    @GetMapping("/verify-email-test-fallback")
    public String testVerificationFallback(Model model) {
        // Don't set success attribute to test fallback state
        model.addAttribute("message", "Test: This is the fallback state when success attribute is not set.");
        model.addAttribute("pageTitle", "Test - Fallback State");
        return "verification/email-verification-result";
    }
}
package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.model.User;
import io.factorialsystems.authorizationserver2.model.VerificationToken;
import io.factorialsystems.authorizationserver2.service.EmailNotificationService;
import io.factorialsystems.authorizationserver2.service.UserService;
import io.factorialsystems.authorizationserver2.service.VerificationService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

@Slf4j
@Controller
@RequiredArgsConstructor
public class LoginController {

	private final UserService userService;
	private final VerificationService verificationService;
	private final EmailNotificationService emailNotificationService;

	/**
	 * Display login page with optional error messages
	 */
	@GetMapping("/login")
	public String login(
			@RequestParam(value = "error", required = false) String error,
			@RequestParam(value = "errorType", required = false) String errorType,
			@RequestParam(value = "errorMessage", required = false) String errorMessage,
			@RequestParam(value = "userId", required = false) String userId,
			@RequestParam(value = "email", required = false) String email,
			@RequestParam(value = "username", required = false) String username,
			@RequestParam(value = "success", required = false) String success,
			@RequestParam(value = "successMessage", required = false) String successMessage,
			Model model) {

		// Handle error parameters
		if ("true".equals(error) && errorMessage != null) {
			String decodedMessage = URLDecoder.decode(errorMessage, StandardCharsets.UTF_8);
			model.addAttribute("errorMessage", decodedMessage);
			model.addAttribute("errorType", errorType);

			// If unverified user, add additional attributes for resend functionality
			if ("unverified".equals(errorType) && userId != null) {
				model.addAttribute("unverifiedUserId", userId);
				if (email != null) {
					model.addAttribute("unverifiedEmail", URLDecoder.decode(email, StandardCharsets.UTF_8));
				}
			}

			// Preserve username for user convenience (except for unverified users)
			if (username != null && !"unverified".equals(errorType)) {
				model.addAttribute("username", URLDecoder.decode(username, StandardCharsets.UTF_8));
			}
		}

		// Handle success parameters (e.g., after email verification resent)
		if ("true".equals(success) && successMessage != null) {
			String decodedMessage = URLDecoder.decode(successMessage, StandardCharsets.UTF_8);
			model.addAttribute("successMessage", decodedMessage);
		}

		return "login";
	}

	/**
	 * Resend verification email for unverified users
	 */
	@PostMapping("/resend-verification")
	public ResponseEntity<Map<String, Object>> resendVerification(@RequestParam("userId") String userId) {
		Map<String, Object> response = new HashMap<>();

		try {
			log.info("Resend verification request for user: {}", userId);

			// Get user
			User user = userService.findById(userId);
			if (user == null) {
				log.warn("User not found for resend verification: {}", userId);
				response.put("success", false);
				response.put("message", "User not found. Please try registering again.");
				return ResponseEntity.badRequest().body(response);
			}

			// Check if already verified
			if (user.getIsEmailVerified()) {
				log.info("User already verified, no need to resend: {}", userId);
				response.put("success", true);
				response.put("message", "Your email is already verified. You can now login.");
				return ResponseEntity.ok(response);
			}

			// Generate new verification token
			VerificationToken token = verificationService.generateEmailVerificationToken(user.getId(), user.getEmail());

			// Send verification email
			emailNotificationService.sendEmailVerification(user, token.getToken());

			log.info("Verification email resent successfully for user: {} ({})", userId, user.getEmail());

			response.put("success", true);
			response.put("message", "Verification email sent! Please check your inbox and spam folder.");
			return ResponseEntity.ok(response);

		} catch (IllegalStateException e) {
			// Rate limiting exceeded
			log.warn("Rate limit exceeded for resend verification: {}", userId);
			response.put("success", false);
			response.put("message", e.getMessage());
			return ResponseEntity.badRequest().body(response);

		} catch (Exception e) {
			log.error("Error resending verification email for user: {}", userId, e);
			response.put("success", false);
			response.put("message", "An error occurred while sending the verification email. Please try again later.");
			return ResponseEntity.internalServerError().body(response);
		}
	}
}

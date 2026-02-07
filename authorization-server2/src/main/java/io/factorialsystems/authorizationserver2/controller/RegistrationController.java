package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.dto.TenantRegistrationRequest;
import io.factorialsystems.authorizationserver2.service.RegistrationService;
import io.factorialsystems.authorizationserver2.service.TenantService;
import io.factorialsystems.authorizationserver2.service.UserService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

@Slf4j
@Controller
@RequiredArgsConstructor
public class RegistrationController {

    private final TenantService tenantService;
    private final UserService userService;
    private final RegistrationService registrationService;

    @GetMapping("/register")
    public String showRegistrationForm(Model model) {
        model.addAttribute("tenantRequest", new TenantRegistrationRequest());
        return "register/tenant-registration";
    }

    @PostMapping("/register")
    public String processRegistration(@Valid @ModelAttribute("tenantRequest") TenantRegistrationRequest request,
                                    BindingResult bindingResult,
                                    Model model,
                                    RedirectAttributes redirectAttributes) {

        log.info("Processing registration for organization: {}", request.getName());

        // Validate form
        if (bindingResult.hasErrors()) {
            log.debug("Registration form has validation errors: {}", bindingResult.getAllErrors());
            return "register/tenant-registration";
        }

        // Additional business logic validation
        try {
            validateRegistrationRequest(request, bindingResult);
            if (bindingResult.hasErrors()) {
                return "register/tenant-registration";
            }

            // Create tenant and user atomically via RegistrationService
            RegistrationService.RegistrationResult result = registrationService.registerTenant(
                request.getName(),
                request.getDomainNormalized(),
                request.getAdminUsername(),
                request.getAdminEmail(),
                request.getAdminPassword(),
                request.getAdminFirstName(),
                request.getAdminLastName()
            );

            // Prepare success page data
            model.addAttribute("tenant", result.tenant());
            model.addAttribute("successMessage",
                "Your organization has been successfully registered! " +
                "A verification email has been sent to " + request.getAdminEmail() + ". " +
                "Please check your email and click the verification link to activate your account.");

            return "register/registration-success";

        } catch (Exception e) {
            log.error("Registration failed for organization: {}", request.getName(), e);
            model.addAttribute("errorMessage",
                "Registration failed: " + e.getMessage() + ". Please try again.");
            return "register/tenant-registration";
        }
    }

    private void validateRegistrationRequest(TenantRegistrationRequest request, BindingResult bindingResult) {
        // Check if domain is already taken (only if provided)
        if (request.getDomainNormalized() != null && !request.getDomainNormalized().isEmpty()) {
            if (!tenantService.isDomainAvailable(request.getDomainNormalized())) {
                bindingResult.rejectValue("domain", "domain.taken",
                    "A tenant with this domain already exists");
            }
        }

        // Check if organization name is already taken
        if (!tenantService.isNameAvailable(request.getName())) {
            bindingResult.rejectValue("name", "name.taken",
                "A tenant with this name already exists");
        }

        // Check if username is already taken
        if (!userService.isUsernameAvailable(request.getAdminUsername())) {
            bindingResult.rejectValue("adminUsername", "username.taken",
                "This username is already taken");
        }

        // Check if email is already taken
        if (!userService.isEmailAvailable(request.getAdminEmail())) {
            bindingResult.rejectValue("adminEmail", "email.taken",
                "A user with this email already exists");
        }

    }
}

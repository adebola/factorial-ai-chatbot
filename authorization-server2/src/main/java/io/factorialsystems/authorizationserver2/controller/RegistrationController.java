package io.factorialsystems.authorizationserver2.controller;

import io.factorialsystems.authorizationserver2.dto.TenantRegistrationRequest;
import io.factorialsystems.authorizationserver2.model.Tenant;
import io.factorialsystems.authorizationserver2.model.User;
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
        
        log.info("Processing registration for organization: {} ({})", request.getName(), request.getDomain());
        
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
            
            // Create tenant and user
            RegistrationResult result = createTenantRegistration(request);
            
            // Prepare success page data
            model.addAttribute("tenant", result.tenant());
            model.addAttribute("successMessage", 
                "Your organization has been successfully registered! " +
                (request.hasAdminPassword() ? 
                    "You can now sign in with your credentials." :
                    "An invitation email has been sent to set up your admin account."));
            
            return "register/registration-success";
            
        } catch (Exception e) {
            log.error("Registration failed for organization: {} ({})", request.getName(), request.getDomain(), e);
            model.addAttribute("errorMessage", 
                "Registration failed: " + e.getMessage() + ". Please try again.");
            return "register/tenant-registration";
        }
    }
    
    private void validateRegistrationRequest(TenantRegistrationRequest request, BindingResult bindingResult) {
        // Check if domain is already taken
        if (!tenantService.isDomainAvailable(request.getDomainNormalized())) {
            bindingResult.rejectValue("domain", "domain.taken", 
                "A tenant with this domain already exists");
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
    
    private boolean isValidUrl(String url) {
        try {
            // Basic URL validation
            return url.matches("^https?://.*") && url.length() > 10;
        } catch (Exception e) {
            return false;
        }
    }
    
    private RegistrationResult createTenantRegistration(TenantRegistrationRequest request) {
        // 1. Create tenant
        Tenant tenant = tenantService.createTenant(
            request.getName(), 
            request.getDomainNormalized(), 
            null // No longer using description field
        );
        
        // 2. Create admin user
        User adminUser = userService.createAdminUser(
            tenant.getId(),
            request.getAdminUsername(),
            request.getAdminEmail(),
            request.getAdminPassword(),
            request.getAdminFirstName(),
            request.getAdminLastName()
        );
        
        log.info("Successfully completed registration for tenant: {} ({})", tenant.getName(), tenant.getDomain());
        
        return new RegistrationResult(tenant, adminUser);
    }

    // Helper class to return registration results
    private record RegistrationResult(Tenant tenant, User adminUser) {

    }
}
package io.factorialsystems.authorizationserver.web;

import io.factorialsystems.authorizationserver.dto.TenantCreateRequest;
import io.factorialsystems.authorizationserver.dto.TenantResponse;
import io.factorialsystems.authorizationserver.service.TenantService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import java.util.List;

/**
 * Web controller for tenant registration and management pages
 */
@Slf4j
@Controller
@RequestMapping("/register")
@RequiredArgsConstructor
public class TenantWebController {
    
    private final TenantService tenantService;
    
    /**
     * Show tenant registration form
     */
    @GetMapping
    public String showRegistrationForm(Model model) {
        log.debug("Showing tenant registration form");
        
        if (!model.containsAttribute("tenantRequest")) {
            model.addAttribute("tenantRequest", new TenantCreateRequest());
        }
        
        return "register/tenant-registration";
    }
    
    /**
     * Process tenant registration
     */
    @PostMapping
    public String registerTenant(@Valid @ModelAttribute("tenantRequest") TenantCreateRequest request,
                                BindingResult bindingResult,
                                Model model,
                                RedirectAttributes redirectAttributes) {
        
        log.info("Processing tenant registration for: {}", request.getName());
        
        if (bindingResult.hasErrors()) {
            log.debug("Validation errors in tenant registration: {}", bindingResult.getAllErrors());
            return "register/tenant-registration";
        }
        
        try {
            TenantResponse response = tenantService.createTenant(request);
            
            log.info("Successfully registered tenant: {} with ID: {}", response.getName(), response.getId());
            
            // Add success message and tenant info for confirmation page
            redirectAttributes.addFlashAttribute("successMessage", "Tenant registered successfully!");
            redirectAttributes.addFlashAttribute("tenant", response);
            redirectAttributes.addFlashAttribute("clientCredentials", 
                    new ClientCredentials(response.getClientId(), "Client secret will be provided separately"));
            
            return "redirect:/register/success";
            
        } catch (IllegalArgumentException e) {
            log.warn("Invalid tenant registration: {}", e.getMessage());
            model.addAttribute("errorMessage", e.getMessage());
            return "register/tenant-registration";
            
        } catch (Exception e) {
            log.error("Error registering tenant: {}", request.getName(), e);
            model.addAttribute("errorMessage", "Registration failed. Please try again.");
            return "register/tenant-registration";
        }
    }
    
    /**
     * Show registration success page
     */
    @GetMapping("/success")
    public String registrationSuccess(Model model) {
        log.debug("Showing registration success page");
        
        // Check if we have tenant info from redirect
        if (!model.containsAttribute("tenant")) {
            log.warn("Registration success page accessed without tenant information");
            return "redirect:/register";
        }
        
        return "register/registration-success";
    }
    
    /**
     * Show tenant information page (for existing tenants)
     */
    @GetMapping("/info")
    public String tenantInfo(@RequestParam(required = false) String domain,
                            @RequestParam(required = false) String client_id,
                            Model model) {
        
        log.debug("Showing tenant info for domain: {}, client_id: {}", domain, client_id);
        
        try {
            TenantResponse tenant = null;
            
            if (domain != null) {
                // TODO: Add method to find by domain
                log.debug("Looking up tenant by domain: {}", domain);
            } else if (client_id != null) {
                // TODO: Add method to find by client_id  
                log.debug("Looking up tenant by client_id: {}", client_id);
            }
            
            if (tenant != null) {
                model.addAttribute("tenant", tenant);
                return "register/tenant-info";
            } else {
                model.addAttribute("errorMessage", "Tenant not found");
                return "register/tenant-not-found";
            }
            
        } catch (Exception e) {
            log.error("Error retrieving tenant info", e);
            model.addAttribute("errorMessage", "Error retrieving tenant information");
            return "error";
        }
    }
    
    /**
     * Helper class for client credentials display
     */
    public static class ClientCredentials {
        private final String clientId;
        private final String clientSecret;
        
        public ClientCredentials(String clientId, String clientSecret) {
            this.clientId = clientId;
            this.clientSecret = clientSecret;
        }
        
        public String getClientId() { return clientId; }
        public String getClientSecret() { return clientSecret; }
    }
}
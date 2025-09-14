package io.factorialsystems.authorizationserver.web;

import io.factorialsystems.authorizationserver.service.TenantResolutionService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;

/**
 * Web controller for authentication pages (login, consent, error)
 */
@Slf4j
@Controller
@RequiredArgsConstructor
public class AuthController {
    
    private final TenantResolutionService tenantResolutionService;
    
    /**
     * Login page - Direct user authentication without tenant selection
     */
    @GetMapping("/login")
    public String login(@RequestParam(value = "error", required = false) String error,
                       @RequestParam(value = "logout", required = false) String logout,
                       Model model) {
        
        log.debug("Rendering login page with error: {}, logout: {}", error, logout);
        
        // Add error/success messages
        if (error != null) {
            model.addAttribute("errorMessage", "Invalid username or password");
        }
        if (logout != null) {
            model.addAttribute("successMessage", "You have been successfully logged out");
        }
        
        return "login";
    }
    
    /**
     * OAuth2 consent page
     */
    @GetMapping("/oauth2/consent")
    public String consent(@RequestParam(value = "scope", required = false) String scope,
                         @RequestParam(value = "state", required = false) String state,
                         @RequestParam(value = "client_id", required = false) String clientId,
                         Model model) {
        
        log.debug("Rendering consent page for client: {}, scopes: {}", clientId, scope);
        
        // Resolve client/tenant information
        if (clientId != null) {
            String tenantId = tenantResolutionService.resolveTenantByClientId(clientId);
            if (tenantId != null) {
                tenantResolutionService.getTenantById(tenantId).ifPresent(tenant -> {
                    model.addAttribute("clientName", tenant.getName());
                    model.addAttribute("tenantName", tenant.getName());
                    model.addAttribute("tenantDomain", tenant.getDomain());
                });
            }
        }
        
        // Parse and add scopes
        if (scope != null) {
            String[] scopes = scope.split(" ");
            model.addAttribute("requestedScopes", scopes);
        }
        
        model.addAttribute("clientId", clientId);
        model.addAttribute("state", state);
        
        return "consent";
    }
    
    /**
     * Error page
     */
    @GetMapping("/error")
    public String error(@RequestParam(value = "error", required = false) String error,
                       @RequestParam(value = "error_description", required = false) String errorDescription,
                       Model model) {
        
        log.debug("Rendering error page with error: {}, description: {}", error, errorDescription);
        
        model.addAttribute("error", error != null ? error : "Unknown error");
        model.addAttribute("errorDescription", errorDescription != null ? errorDescription : "An unexpected error occurred");
        
        return "error";
    }
    
    /**
     * Home page (after login)
     */
    @GetMapping({"/", "/home"})
    public String home(Model model) {
        // No tenant context needed on home page - tenant info comes from JWT token
        return "home";
    }
    
}
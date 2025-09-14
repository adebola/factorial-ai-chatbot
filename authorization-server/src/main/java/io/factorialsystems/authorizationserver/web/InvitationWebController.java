package io.factorialsystems.authorizationserver.web;

import io.factorialsystems.authorizationserver.dto.AcceptInvitationRequest;
import io.factorialsystems.authorizationserver.dto.InvitationResponse;
import io.factorialsystems.authorizationserver.dto.UserResponse;
import io.factorialsystems.authorizationserver.service.InvitationService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import java.util.Optional;

/**
 * Web controller for invitation acceptance pages
 */
@Slf4j
@Controller
@RequestMapping("/invitation")
@RequiredArgsConstructor
public class InvitationWebController {
    
    private final InvitationService invitationService;
    
    /**
     * Show invitation details and acceptance form
     */
    @GetMapping("/accept")
    public String showInvitationForm(@RequestParam String token, Model model) {
        log.debug("Showing invitation acceptance form for token: {}", token);
        
        try {
            Optional<InvitationResponse> invitationOpt = invitationService.getInvitationByToken(token);
            
            if (invitationOpt.isEmpty()) {
                log.warn("Invalid or expired invitation token: {}", token);
                model.addAttribute("errorMessage", "Invalid or expired invitation link");
                return "invitation/invalid-invitation";
            }
            
            InvitationResponse invitation = invitationOpt.get();
            
            // Check if invitation is expired
            if (invitation.getIsExpired()) {
                log.warn("Expired invitation token: {}", token);
                model.addAttribute("invitation", invitation);
                model.addAttribute("errorMessage", "This invitation has expired");
                return "invitation/expired-invitation";
            }
            
            // Check if invitation is already accepted
            if (invitation.getStatus() == InvitationResponse.InvitationStatus.ACCEPTED) {
                log.info("Invitation already accepted for token: {}", token);
                model.addAttribute("invitation", invitation);
                model.addAttribute("successMessage", "This invitation has already been accepted");
                return "invitation/already-accepted";
            }
            
            // Show acceptance form
            model.addAttribute("invitation", invitation);
            if (!model.containsAttribute("acceptRequest")) {
                AcceptInvitationRequest acceptRequest = new AcceptInvitationRequest();
                acceptRequest.setInvitationToken(token);
                acceptRequest.setFirstName(invitation.getFirstName());
                acceptRequest.setLastName(invitation.getLastName());
                model.addAttribute("acceptRequest", acceptRequest);
            }
            
            return "invitation/accept-invitation";
            
        } catch (Exception e) {
            log.error("Error showing invitation form for token: {}", token, e);
            model.addAttribute("errorMessage", "Error processing invitation");
            return "error";
        }
    }
    
    /**
     * Process invitation acceptance
     */
    @PostMapping("/accept")
    public String acceptInvitation(@Valid @ModelAttribute("acceptRequest") AcceptInvitationRequest request,
                                  BindingResult bindingResult,
                                  Model model,
                                  RedirectAttributes redirectAttributes) {
        
        log.info("Processing invitation acceptance for token: {}", request.getInvitationToken());
        
        try {
            // Get invitation details for form validation
            Optional<InvitationResponse> invitationOpt = invitationService.getInvitationByToken(request.getInvitationToken());
            if (invitationOpt.isEmpty()) {
                model.addAttribute("errorMessage", "Invalid or expired invitation");
                return "invitation/invalid-invitation";
            }
            
            InvitationResponse invitation = invitationOpt.get();
            model.addAttribute("invitation", invitation);
            
            if (bindingResult.hasErrors()) {
                log.debug("Validation errors in invitation acceptance: {}", bindingResult.getAllErrors());
                return "invitation/accept-invitation";
            }
            
            // Additional password validation
            if (!request.isPasswordValid()) {
                model.addAttribute("errorMessage", "Passwords do not match");
                return "invitation/accept-invitation";
            }
            
            // Accept the invitation
            UserResponse user = invitationService.acceptInvitation(request);
            
            log.info("Successfully accepted invitation for user: {} in tenant: {}", 
                    user.getUsername(), user.getTenantId());
            
            // Add success information for confirmation page
            redirectAttributes.addFlashAttribute("successMessage", "Account created successfully! You can now log in.");
            redirectAttributes.addFlashAttribute("user", user);
            redirectAttributes.addFlashAttribute("invitation", invitation);
            
            return "redirect:/invitation/success";
            
        } catch (IllegalArgumentException e) {
            log.warn("Invalid invitation acceptance: {}", e.getMessage());
            
            // Re-get invitation for display
            Optional<InvitationResponse> invitationOpt = invitationService.getInvitationByToken(request.getInvitationToken());
            invitationOpt.ifPresent(inv -> model.addAttribute("invitation", inv));
            
            model.addAttribute("errorMessage", e.getMessage());
            return "invitation/accept-invitation";
            
        } catch (Exception e) {
            log.error("Error accepting invitation", e);
            
            // Re-get invitation for display
            Optional<InvitationResponse> invitationOpt = invitationService.getInvitationByToken(request.getInvitationToken());
            invitationOpt.ifPresent(inv -> model.addAttribute("invitation", inv));
            
            model.addAttribute("errorMessage", "Failed to create account. Please try again.");
            return "invitation/accept-invitation";
        }
    }
    
    /**
     * Show invitation acceptance success page
     */
    @GetMapping("/success")
    public String invitationSuccess(Model model) {
        log.debug("Showing invitation success page");
        
        // Check if we have user info from redirect
        if (!model.containsAttribute("user")) {
            log.warn("Invitation success page accessed without user information");
            return "redirect:/login";
        }
        
        return "invitation/invitation-success";
    }
    
    /**
     * Show invalid invitation page
     */
    @GetMapping("/invalid")
    public String invalidInvitation(@RequestParam(required = false) String message, Model model) {
        log.debug("Showing invalid invitation page with message: {}", message);
        
        if (message != null) {
            model.addAttribute("errorMessage", message);
        } else {
            model.addAttribute("errorMessage", "The invitation link is invalid or has expired");
        }
        
        return "invitation/invalid-invitation";
    }
    
    /**
     * Show expired invitation page
     */
    @GetMapping("/expired")
    public String expiredInvitation(@RequestParam(required = false) String token, Model model) {
        log.debug("Showing expired invitation page for token: {}", token);
        
        if (token != null) {
            // Try to get invitation details even if expired for display purposes
            try {
                Optional<InvitationResponse> invitationOpt = invitationService.getInvitationByToken(token);
                invitationOpt.ifPresent(invitation -> model.addAttribute("invitation", invitation));
            } catch (Exception e) {
                log.debug("Could not retrieve expired invitation details", e);
            }
        }
        
        model.addAttribute("errorMessage", "This invitation has expired. Please contact your administrator for a new invitation.");
        
        return "invitation/expired-invitation";
    }
}
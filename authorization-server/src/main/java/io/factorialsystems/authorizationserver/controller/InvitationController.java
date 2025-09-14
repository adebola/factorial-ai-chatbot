package io.factorialsystems.authorizationserver.controller;

import io.factorialsystems.authorizationserver.dto.AcceptInvitationRequest;
import io.factorialsystems.authorizationserver.dto.InvitationRequest;
import io.factorialsystems.authorizationserver.dto.InvitationResponse;
import io.factorialsystems.authorizationserver.dto.UserResponse;
import io.factorialsystems.authorizationserver.service.InvitationService;
import io.factorialsystems.authorizationserver.service.MultiTenantUserDetails;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.Optional;

/**
 * REST controller for user invitation operations
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/invitations")
@RequiredArgsConstructor
public class InvitationController {
    
    private final InvitationService invitationService;
    
    /**
     * Invite a new user to the tenant
     * Only tenant admins can invite users to their tenant
     */
    @PostMapping
    @PreAuthorize("hasRole('TENANT_ADMIN')")
    public ResponseEntity<InvitationResponse> inviteUser(@Valid @RequestBody InvitationRequest request,
                                                        Authentication authentication) {
        log.info("Inviting user: {}", request.getEmail());
        
        try {
            MultiTenantUserDetails userDetails = (MultiTenantUserDetails) authentication.getPrincipal();
            String tenantId = userDetails.getTenantId();
            String invitedBy = userDetails.getUserId();
            
            InvitationResponse response = invitationService.inviteUser(tenantId, invitedBy, request);
            return ResponseEntity.status(HttpStatus.CREATED).body(response);
            
        } catch (IllegalArgumentException e) {
            log.warn("Invalid invitation request: {}", e.getMessage());
            return ResponseEntity.badRequest().build();
        } catch (Exception e) {
            log.error("Error inviting user: {}", request.getEmail(), e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Accept invitation and set up user account
     * This endpoint is public (no authentication required)
     */
    @PostMapping("/accept")
    public ResponseEntity<UserResponse> acceptInvitation(@Valid @RequestBody AcceptInvitationRequest request) {
        log.info("Accepting invitation with token: {}", request.getInvitationToken());
        
        try {
            UserResponse response = invitationService.acceptInvitation(request);
            return ResponseEntity.ok(response);
            
        } catch (IllegalArgumentException e) {
            log.warn("Invalid invitation acceptance: {}", e.getMessage());
            return ResponseEntity.badRequest().build();
        } catch (Exception e) {
            log.error("Error accepting invitation", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Get invitation details by token
     * This endpoint is public (no authentication required) for invitation validation
     */
    @GetMapping("/token/{token}")
    public ResponseEntity<InvitationResponse> getInvitationByToken(@PathVariable String token) {
        log.debug("Getting invitation by token: {}", token);
        
        try {
            Optional<InvitationResponse> invitation = invitationService.getInvitationByToken(token);
            return invitation.map(ResponseEntity::ok)
                           .orElse(ResponseEntity.notFound().build());
        } catch (Exception e) {
            log.error("Error getting invitation by token", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * List pending invitations for current tenant
     * Only tenant admins can view pending invitations
     */
    @GetMapping("/pending")
    @PreAuthorize("hasRole('TENANT_ADMIN')")
    public ResponseEntity<List<InvitationResponse>> getPendingInvitations(Authentication authentication) {
        log.debug("Getting pending invitations for tenant");
        
        try {
            MultiTenantUserDetails userDetails = (MultiTenantUserDetails) authentication.getPrincipal();
            String tenantId = userDetails.getTenantId();
            
            List<InvitationResponse> invitations = invitationService.getPendingInvitations(tenantId);
            return ResponseEntity.ok(invitations);
            
        } catch (Exception e) {
            log.error("Error getting pending invitations", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Resend invitation email
     * Only tenant admins can resend invitations in their tenant
     */
    @PostMapping("/{userId}/resend")
    @PreAuthorize("hasRole('TENANT_ADMIN')")
    public ResponseEntity<Void> resendInvitation(@PathVariable String userId,
                                               Authentication authentication) {
        log.info("Resending invitation for user: {}", userId);
        
        try {
            MultiTenantUserDetails userDetails = (MultiTenantUserDetails) authentication.getPrincipal();
            String tenantId = userDetails.getTenantId();
            String resendBy = userDetails.getUserId();
            
            boolean success = invitationService.resendInvitation(userId, tenantId, resendBy);
            return success ? ResponseEntity.ok().build() 
                          : ResponseEntity.notFound().build();
                          
        } catch (Exception e) {
            log.error("Error resending invitation for user: {}", userId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Cancel pending invitation
     * Only tenant admins can cancel invitations in their tenant
     */
    @DeleteMapping("/{userId}")
    @PreAuthorize("hasRole('TENANT_ADMIN')")
    public ResponseEntity<Void> cancelInvitation(@PathVariable String userId,
                                               Authentication authentication) {
        log.info("Cancelling invitation for user: {}", userId);
        
        try {
            MultiTenantUserDetails userDetails = (MultiTenantUserDetails) authentication.getPrincipal();
            String tenantId = userDetails.getTenantId();
            
            boolean success = invitationService.cancelInvitation(userId, tenantId);
            return success ? ResponseEntity.noContent().build() 
                          : ResponseEntity.notFound().build();
                          
        } catch (Exception e) {
            log.error("Error cancelling invitation for user: {}", userId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Clean up expired invitations
     * Only global admins can trigger cleanup operations
     */
    @PostMapping("/cleanup")
    @PreAuthorize("hasRole('GLOBAL_ADMIN')")
    public ResponseEntity<String> cleanupExpiredInvitations() {
        log.info("Cleaning up expired invitations");
        
        try {
            int cleaned = invitationService.cleanupExpiredInvitations();
            return ResponseEntity.ok(String.format("Cleaned up %d expired invitations", cleaned));
            
        } catch (Exception e) {
            log.error("Error cleaning up expired invitations", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Health check endpoint for invitation service
     */
    @GetMapping("/health")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("Invitation service is healthy");
    }
}
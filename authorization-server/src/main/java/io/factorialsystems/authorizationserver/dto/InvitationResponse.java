package io.factorialsystems.authorizationserver.dto;

import lombok.Builder;
import lombok.Getter;
import lombok.Setter;
import lombok.ToString;


import java.time.LocalDateTime;

/**
 * DTO for invitation response data
 */
@Getter
@Setter
@ToString
@Builder
public class InvitationResponse {
    
    private String id;
    private String tenantId;
    private String tenantName;
    private String username;
    private String email;
    private String firstName;
    private String lastName;
    private Boolean isTenantAdmin;
    
    // Invitation details
    private String invitationToken;
    private LocalDateTime invitationSentAt;
    private LocalDateTime invitationExpiresAt;
    private String invitedBy;
    private String invitedByUsername;
    private String message;
    
    // Status
    private InvitationStatus status;
    private Boolean isExpired;
    private LocalDateTime acceptedAt;
    
    public enum InvitationStatus {
        PENDING,     // Invitation sent, waiting for acceptance
        ACCEPTED,    // User has accepted and set password
        EXPIRED,     // Invitation has expired
        CANCELLED    // Invitation was cancelled
    }
}
package io.factorialsystems.authorizationserver.service;

import io.factorialsystems.authorizationserver.dto.AcceptInvitationRequest;
import io.factorialsystems.authorizationserver.dto.InvitationRequest;
import io.factorialsystems.authorizationserver.dto.InvitationResponse;
import io.factorialsystems.authorizationserver.dto.UserResponse;
import io.factorialsystems.authorizationserver.mapper.*;
import io.factorialsystems.authorizationserver.model.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * Service for managing user invitations via email.
 * Handles global user uniqueness and email conflict resolution for loose-multitenant pattern.
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class InvitationService {
    
    private final UserMapper userMapper;
    private final TenantMapper tenantMapper;
    private final RoleMapper roleMapper;
    private final UserRoleMapper userRoleMapper;
    private final AuditLogMapper auditLogMapper;
    private final PasswordEncoder passwordEncoder;
    // TODO: Inject email service when available
    // private final EmailService emailService;
    
    /**
     * Send an invitation to a new user
     */
    @Transactional
    public InvitationResponse inviteUser(String tenantId, String invitedBy, InvitationRequest request) {
        log.info("Inviting user: {} to tenant: {}", request.getEmail(), tenantId);
        
        try {
            // Validate tenant exists and is active
            Optional<Tenant> tenantOpt = tenantMapper.findById(tenantId);
            if (tenantOpt.isEmpty() || !tenantOpt.get().getIsActive()) {
                throw new IllegalArgumentException("Tenant not found or inactive: " + tenantId);
            }
            Tenant tenant = tenantOpt.get();
            
            // Handle global uniqueness constraints for loose-multitenant pattern
            String finalEmail = request.getEmail();
            String finalUsername = request.getUsername();
            
            // Check and resolve email conflicts globally
            if (userMapper.existsByEmailGlobally(request.getEmail())) {
                log.info("Email {} already exists globally, generating unique variant for tenant {}", 
                        request.getEmail(), tenant.getDomain());
                finalEmail = userMapper.generateUniqueInvitationEmail(request.getEmail(), tenant.getDomain());
                log.info("Generated unique email: {}", finalEmail);
            }
            
            // Check and resolve username conflicts globally  
            if (userMapper.existsByUsernameGlobally(request.getUsername())) {
                log.info("Username {} already exists globally, generating unique variant for tenant {}", 
                        request.getUsername(), tenant.getDomain());
                finalUsername = userMapper.generateUniqueUsername(request.getUsername(), tenant.getDomain());
                log.info("Generated unique username: {}", finalUsername);
            }
            
            // Generate invitation token
            String invitationToken = UUID.randomUUID().toString();
            String userId = UUID.randomUUID().toString();
            
            // Calculate expiration date
            LocalDateTime expiresAt = LocalDateTime.now().plusDays(request.getValidityDays());
            
            // Create user with invitation token using final (possibly modified) email and username
            User user = User.builder()
                    .id(userId)
                    .tenantId(tenantId)
                    .username(finalUsername)
                    .email(finalEmail)
                    .firstName(request.getFirstName())
                    .lastName(request.getLastName())
                    .isActive(true)
                    .isTenantAdmin(request.getIsTenantAdmin() != null ? request.getIsTenantAdmin() : false)
                    .emailVerified(false) // Will be verified when the invitation is accepted
                    .accountLocked(false)
                    .invitationToken(invitationToken)
                    .invitationExpiresAt(expiresAt)
                    .invitedBy(invitedBy)
                    .failedLoginAttempts(0)
                    .createdAt(LocalDateTime.now())
                    .updatedAt(LocalDateTime.now())
                    .build();
            
            int userRows = userMapper.insertUser(user);
            if (userRows == 0) {
                throw new RuntimeException("Failed to create invited user");
            }
            
            // Assign roles to user
            assignRolesToInvitedUser(userId, tenantId, request);
            
            // Send invitation email (to the final email address)
            sendInvitationEmail(user, tenant, invitedBy, request.getMessage());
            
            // Log invitation
            logUserInvitation(tenantId, userId, invitedBy);
            
            log.info("Successfully invited user: {} (final email: {}) to tenant: {}", 
                    request.getEmail(), finalEmail, tenantId);
            
            return buildInvitationResponse(user, tenant, invitedBy);
            
        } catch (Exception e) {
            log.error("Error inviting user: {} to tenant: {}", request.getEmail(), tenantId, e);
            throw new RuntimeException("Failed to invite user: " + e.getMessage(), e);
        }
    }
    
    /**
     * Accept invitation and set up user account
     */
    @Transactional
    public UserResponse acceptInvitation(AcceptInvitationRequest request) {
        log.info("Accepting invitation with token: {}", request.getInvitationToken());
        
        try {
            // Validate password confirmation
            if (!request.isPasswordValid()) {
                throw new IllegalArgumentException("Password and confirmation do not match");
            }
            
            // Find user by invitation token
            Optional<User> userOpt = userMapper.findByValidInvitationToken(request.getInvitationToken());
            if (userOpt.isEmpty()) {
                throw new IllegalArgumentException("Invalid or expired invitation token");
            }
            
            User user = userOpt.get();
            
            // Update user with password and clear invitation token
            user.setPasswordHash(passwordEncoder.encode(request.getPassword()));
            user.setInvitationToken(null);
            user.setInvitationExpiresAt(null);
            user.setEmailVerified(true);
            
            // Update first name and last name if provided
            if (request.getFirstName() != null && !request.getFirstName().trim().isEmpty()) {
                user.setFirstName(request.getFirstName().trim());
            }
            if (request.getLastName() != null && !request.getLastName().trim().isEmpty()) {
                user.setLastName(request.getLastName().trim());
            }
            
            int rows = userMapper.updatePasswordAndClearInvitation(user.getId(), user.getTenantId(), user.getPasswordHash());
            if (rows == 0) {
                throw new RuntimeException("Failed to accept invitation");
            }
            
            // Log invitation acceptance
            logInvitationAcceptance(user.getTenantId(), user.getId());
            
            log.info("Successfully accepted invitation for user: {} in tenant: {}", user.getUsername(), user.getTenantId());
            
            // Build and return user response
            return buildUserResponse(user);
            
        } catch (Exception e) {
            log.error("Error accepting invitation", e);
            throw new RuntimeException("Failed to accept invitation: " + e.getMessage(), e);
        }
    }
    
    /**
     * Get invitation details by token
     */
    @Transactional(readOnly = true)
    public Optional<InvitationResponse> getInvitationByToken(String token) {
        try {
            Optional<User> userOpt = userMapper.findByValidInvitationToken(token);
            if (userOpt.isEmpty()) {
                return Optional.empty();
            }
            
            User user = userOpt.get();
            Optional<Tenant> tenantOpt = tenantMapper.findById(user.getTenantId());
            if (tenantOpt.isEmpty()) {
                return Optional.empty();
            }
            
            return Optional.of(buildInvitationResponse(user, tenantOpt.get(), user.getInvitedBy()));
            
        } catch (Exception e) {
            log.error("Error getting invitation by token", e);
            return Optional.empty();
        }
    }
    
    /**
     * List pending invitations for tenant
     */
    @Transactional(readOnly = true)
    public List<InvitationResponse> getPendingInvitations(String tenantId) {
        try {
            List<User> users = userMapper.findByTenant(tenantId);
            Optional<Tenant> tenantOpt = tenantMapper.findById(tenantId);
            if (tenantOpt.isEmpty()) {
                return List.of();
            }
            Tenant tenant = tenantOpt.get();
            
            return users.stream()
                    .filter(User::hasPendingInvitation)
                    .map(user -> buildInvitationResponse(user, tenant, user.getInvitedBy()))
                    .collect(Collectors.toList());
                    
        } catch (Exception e) {
            log.error("Error getting pending invitations for tenant: {}", tenantId, e);
            return List.of();
        }
    }
    
    /**
     * Resend invitation email
     */
    @Transactional
    public boolean resendInvitation(String userId, String tenantId, String resendBy) {
        log.info("Resending invitation for user: {} in tenant: {}", userId, tenantId);
        
        try {
            Optional<User> userOpt = userMapper.findByIdAndTenant(userId, tenantId);
            if (userOpt.isEmpty() || !userOpt.get().hasPendingInvitation()) {
                return false;
            }
            
            User user = userOpt.get();
            Optional<Tenant> tenantOpt = tenantMapper.findById(tenantId);
            if (tenantOpt.isEmpty()) {
                return false;
            }
            
            // Extend expiration date
            LocalDateTime newExpiration = LocalDateTime.now().plusDays(7);
            user.setInvitationExpiresAt(newExpiration);
            userMapper.updateUser(user);
            
            // Resend email
            sendInvitationEmail(user, tenantOpt.get(), resendBy, "Invitation resent");
            
            log.info("Successfully resent invitation for user: {} in tenant: {}", userId, tenantId);
            return true;
            
        } catch (Exception e) {
            log.error("Error resending invitation for user: {} in tenant: {}", userId, tenantId, e);
            return false;
        }
    }
    
    /**
     * Cancel pending invitation
     */
    @Transactional
    public boolean cancelInvitation(String userId, String tenantId) {
        log.info("Cancelling invitation for user: {} in tenant: {}", userId, tenantId);
        
        try {
            Optional<User> userOpt = userMapper.findByIdAndTenant(userId, tenantId);
            if (userOpt.isEmpty() || !userOpt.get().hasPendingInvitation()) {
                return false;
            }
            
            // Deactivate the user (soft delete)
            int rows = userMapper.deactivateUser(userId, tenantId);
            
            log.info("Successfully cancelled invitation for user: {} in tenant: {}", userId, tenantId);
            return rows > 0;
            
        } catch (Exception e) {
            log.error("Error cancelling invitation for user: {} in tenant: {}", userId, tenantId, e);
            return false;
        }
    }
    
    /**
     * Clean up expired invitations
     */
    @Transactional
    public int cleanupExpiredInvitations() {
        log.info("Cleaning up expired invitations");
        
        try {
            int cleaned = userMapper.cleanupExpiredInvitations();
            log.info("Cleaned up {} expired invitations", cleaned);
            return cleaned;
        } catch (Exception e) {
            log.error("Error cleaning up expired invitations", e);
            return 0;
        }
    }
    
    /**
     * Assign roles to invited user
     */
    private void assignRolesToInvitedUser(String userId, String tenantId, InvitationRequest request) {
        try {
            List<String> roleIds = request.getRoleIds();
            
            if (roleIds == null || roleIds.isEmpty()) {
                // Assign default USER role (global roles now)
                Optional<Role> defaultRoleOpt = roleMapper.findByName("USER");
                if (defaultRoleOpt.isPresent()) {
                    UserRole userRole = UserRole.createPermanent(userId, defaultRoleOpt.get().getId(), null);
                    userRole.setId(UUID.randomUUID().toString());
                    userRoleMapper.insertUserRole(userRole);
                }
            } else {
                // Assign specified roles (all roles are global now, no tenant check needed)
                for (String roleId : roleIds) {
                    Optional<Role> roleOpt = roleMapper.findById(roleId);
                    if (roleOpt.isPresent()) {
                        UserRole userRole = UserRole.createPermanent(userId, roleId, null);
                        userRole.setId(UUID.randomUUID().toString());
                        userRoleMapper.insertUserRole(userRole);
                    }
                }
            }
            
            // If user is tenant admin, assign ADMIN role (global admin role)
            if (request.getIsTenantAdmin() != null && request.getIsTenantAdmin()) {
                Optional<Role> adminRoleOpt = roleMapper.findByName("ADMIN");
                if (adminRoleOpt.isPresent()) {
                    UserRole userRole = UserRole.createPermanent(userId, adminRoleOpt.get().getId(), null);
                    userRole.setId(UUID.randomUUID().toString());
                    userRoleMapper.insertUserRole(userRole);
                }
            }
            
        } catch (Exception e) {
            log.error("Error assigning roles to invited user: {}", userId, e);
            throw new RuntimeException("Failed to assign roles to user", e);
        }
    }
    
    /**
     * Send invitation email (placeholder - will integrate with email service later)
     */
    private void sendInvitationEmail(User user, Tenant tenant, String invitedBy, String customMessage) {
        // TODO: Integrate with actual email service
        log.info("Sending invitation email to: {} for tenant: {}", user.getEmail(), tenant.getName());
        
        try {
            String invitationUrl = buildInvitationUrl(user.getInvitationToken());
            
            // For now, just log the invitation details
            log.info("INVITATION EMAIL:");
            log.info("To: {}", user.getEmail());
            log.info("Subject: Invitation to join {}", tenant.getName());
            log.info("Invitation URL: {}", invitationUrl);
            log.info("Expires: {}", user.getInvitationExpiresAt());
            if (customMessage != null) {
                log.info("Custom message: {}", customMessage);
            }
            
            // TODO: Replace with actual email sending
            // emailService.sendInvitationEmail(user, tenant, invitationUrl, customMessage);
            
        } catch (Exception e) {
            log.error("Error sending invitation email", e);
            // Don't throw exception here - the invitation is already created
        }
    }
    
    /**
     * Build invitation URL
     */
    private String buildInvitationUrl(String token) {
        // TODO: Make this configurable
        String baseUrl = "http://localhost:4200";
        return String.format("%s/auth/accept-invitation?token=%s", baseUrl, token);
    }
    
    /**
     * Build invitation response DTO
     */
    private InvitationResponse buildInvitationResponse(User user, Tenant tenant, String invitedBy) {
        try {
            // Get inviter username
            String inviterUsername = null;
            if (invitedBy != null) {
                Optional<User> inviterOpt = userMapper.findByIdAndTenant(invitedBy, tenant.getId());
                if (inviterOpt.isPresent()) {
                    inviterUsername = inviterOpt.get().getUsername();
                }
            }
            
            // Determine status
            InvitationResponse.InvitationStatus status;
            if (user.hasPendingInvitation()) {
                status = user.getInvitationExpiresAt().isBefore(LocalDateTime.now()) ? 
                        InvitationResponse.InvitationStatus.EXPIRED : 
                        InvitationResponse.InvitationStatus.PENDING;
            } else {
                status = InvitationResponse.InvitationStatus.ACCEPTED;
            }
            
            return InvitationResponse.builder()
                    .id(user.getId())
                    .tenantId(user.getTenantId())
                    .tenantName(tenant.getName())
                    .username(user.getUsername())
                    .email(user.getEmail())
                    .firstName(user.getFirstName())
                    .lastName(user.getLastName())
                    .isTenantAdmin(user.getIsTenantAdmin())
                    .invitationToken(user.getInvitationToken())
                    .invitationSentAt(user.getCreatedAt())
                    .invitationExpiresAt(user.getInvitationExpiresAt())
                    .invitedBy(invitedBy)
                    .invitedByUsername(inviterUsername)
                    .status(status)
                    .isExpired(user.getInvitationExpiresAt() != null && user.getInvitationExpiresAt().isBefore(LocalDateTime.now()))
                    .build();
                    
        } catch (Exception e) {
            log.error("Error building invitation response", e);
            throw new RuntimeException("Failed to build invitation response", e);
        }
    }
    
    /**
     * Build user response DTO
     */
    private UserResponse buildUserResponse(User user) {
        try {
            List<Role> roles = roleMapper.findByUserId(user.getId());
            
            return UserResponse.builder()
                    .id(user.getId())
                    .tenantId(user.getTenantId())
                    .username(user.getUsername())
                    .email(user.getEmail())
                    .firstName(user.getFirstName())
                    .lastName(user.getLastName())
                    .fullName(user.getFullName())
                    .isActive(user.getIsActive())
                    .isTenantAdmin(user.getIsTenantAdmin())
                    .emailVerified(user.getEmailVerified())
                    .accountLocked(user.getAccountLocked())
                    .createdAt(user.getCreatedAt())
                    .updatedAt(user.getUpdatedAt())
                    .build();
                    
        } catch (Exception e) {
            log.error("Error building user response", e);
            throw new RuntimeException("Failed to build user response", e);
        }
    }
    
    /**
     * Log user invitation for audit trail
     */
    private void logUserInvitation(String tenantId, String userId, String invitedBy) {
        try {
            AuditLog auditLog = AuditLog.createUserCreation(tenantId, userId, invitedBy, true);
            auditLog.setId(UUID.randomUUID().toString());
            auditLogMapper.insertAuditLog(auditLog);
        } catch (Exception e) {
            log.error("Failed to log user invitation", e);
        }
    }
    
    /**
     * Log invitation acceptance for audit trail
     */
    private void logInvitationAcceptance(String tenantId, String userId) {
        try {
            AuditLog auditLog = AuditLog.builder()
                    .id(UUID.randomUUID().toString())
                    .tenantId(tenantId)
                    .userId(userId)
                    .eventType("INVITATION_ACCEPTED")
                    .eventDescription("User accepted invitation and set up account")
                    .createdAt(LocalDateTime.now())
                    .build();
            auditLogMapper.insertAuditLog(auditLog);
        } catch (Exception e) {
            log.error("Failed to log invitation acceptance", e);
        }
    }
}
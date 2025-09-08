package io.factorialsystems.authorizationserver2.model;

import lombok.*;

import java.time.OffsetDateTime;
import java.util.List;

@Getter
@Setter
@ToString
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class User {
    private String id;
    private String tenantId;
    private String username;
    private String email;
    private String password;
    private String firstName;
    private String lastName;
    private Boolean isActive;
    private Boolean isEmailVerified;
    private OffsetDateTime lastLoginAt;
    private OffsetDateTime createdAt;
    private OffsetDateTime updatedAt;
    
    // Tenant API key (fetched from tenant table)
    private String apiKey;
    
    // Relationships
    private Tenant tenant;
    private List<Role> roles;
}
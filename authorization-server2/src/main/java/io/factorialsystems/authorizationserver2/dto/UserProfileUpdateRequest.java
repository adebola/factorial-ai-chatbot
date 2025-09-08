package io.factorialsystems.authorizationserver2.dto;

import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Getter
@Setter
@NoArgsConstructor
public class UserProfileUpdateRequest {
    private String firstName;
    private String lastName;
}
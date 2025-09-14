package io.factorialsystems.authorizationserver2.service;

import io.factorialsystems.authorizationserver2.mapper.UserMapper;
import io.factorialsystems.authorizationserver2.model.User;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.OffsetDateTime;

/**
 * Service for handling user activity tracking asynchronously
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class UserActivityService {
    
    private final UserMapper userMapper;
    
    /**
     * Update user's last login timestamp asynchronously
     * This method runs on a separate thread and doesn't block the authentication process
     */
    @Async
    @Transactional
    public void updateLastLoginAsync(User user) {
        try {
            log.debug("Updating last login for user {} asynchronously", user.getUsername());
            
            // Update the timestamps
            user.setLastLoginAt(OffsetDateTime.now());
            user.setUpdatedAt(OffsetDateTime.now());
            
            int updated = userMapper.updateLastLogin(user);
            
            if (updated > 0) {
                log.debug("Successfully updated last login for user {}", user.getUsername());
            } else {
                log.warn("No user found to update last login for user: {}", user.getUsername());
            }
            
        } catch (Exception e) {
            log.error("Error updating last login for user {}: {}", user.getUsername(), e.getMessage(), e);
            // Don't rethrow - this is async and shouldn't affect the main authentication flow
        }
    }
}
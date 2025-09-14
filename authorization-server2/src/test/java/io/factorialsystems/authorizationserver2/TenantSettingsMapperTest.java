package io.factorialsystems.authorizationserver2;

import io.factorialsystems.authorizationserver2.mapper.TenantSettingsMapper;
import io.factorialsystems.authorizationserver2.model.TenantSettings;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest
@ActiveProfiles("test")
class TenantSettingsMapperTest {

    @Autowired
    private TenantSettingsMapper tenantSettingsMapper;

    @Test
    void testJsonTypeHandling() {
        // Test data - Use existing tenant from previous tests
        String tenantId = "9eb23c01-b66a-4e23-8316-4884532d5b04";
        String settingsId = UUID.randomUUID().toString();

        // Create additional settings as Map
        Map<String, Object> additionalSettings = new HashMap<>();
        additionalSettings.put("theme", "dark");
        additionalSettings.put("showTimestamp", true);
        additionalSettings.put("maxMessages", 100);

        // Create tenant settings object
        TenantSettings settings = new TenantSettings();
        settings.setId(settingsId);
        settings.setTenantId(tenantId);
        settings.setPrimaryColor("#FF5733");
        settings.setSecondaryColor("#33FF57");
        settings.setHoverText("Test Chat");
        settings.setWelcomeMessage("Welcome to test");
        settings.setChatWindowTitle("Test Support");
        settings.setCompanyLogoUrl("https://test.com/logo.png");
        settings.setAdditionalSettings(additionalSettings);
        settings.setIsActive(true);

        // Test INSERT operation
        assertDoesNotThrow(() -> tenantSettingsMapper.insert(settings),
            "INSERT should not throw exception with JSON data");

        // Test SELECT operation
        TenantSettings retrieved = tenantSettingsMapper.findByTenantId(tenantId);
        assertNotNull(retrieved, "Should retrieve inserted settings");
        assertEquals(tenantId, retrieved.getTenantId());
        assertNotNull(retrieved.getAdditionalSettings(), "Additional settings should not be null");
        assertEquals("dark", retrieved.getAdditionalSettings().get("theme"));
        assertEquals(true, retrieved.getAdditionalSettings().get("showTimestamp"));
        assertEquals(100, retrieved.getAdditionalSettings().get("maxMessages"));

        // Test UPDATE operation
        additionalSettings.put("newField", "test value");
        additionalSettings.put("maxMessages", 200); // Update existing field
        settings.setAdditionalSettings(additionalSettings);
        settings.setPrimaryColor("#FF0000"); // Also update a regular field

        int updateResult = tenantSettingsMapper.updateByTenantId(settings);
        assertEquals(1, updateResult, "Should update exactly one row");

        // Verify UPDATE worked
        TenantSettings updated = tenantSettingsMapper.findByTenantId(tenantId);
        assertNotNull(updated);
        assertEquals("#FF0000", updated.getPrimaryColor());
        assertEquals("test value", updated.getAdditionalSettings().get("newField"));
        assertEquals(200, updated.getAdditionalSettings().get("maxMessages"));

        System.out.println("✓ MyBatis JSON type handling test passed successfully!");
        System.out.println("✓ INSERT, SELECT, and UPDATE operations work correctly with JSON columns");
    }
}
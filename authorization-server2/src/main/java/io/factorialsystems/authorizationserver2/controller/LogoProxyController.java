package io.factorialsystems.authorizationserver2.controller;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.InputStreamResource;
import org.springframework.http.*;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.client.RestTemplate;
import org.springframework.web.multipart.MultipartFile;

import java.io.ByteArrayInputStream;
import java.util.Map;

/**
 * Proxy controller for logo operations - forwards requests to onboarding service
 * 
 * Note: Uses RestTemplate for service-to-service communication. While WebClient is
 * the recommended replacement, RestTemplate is appropriate for traditional servlet-based
 * Spring Boot applications and is still supported (though in maintenance mode).
 */
@Slf4j
@RestController
@RequestMapping("/api/v1/tenants")
@RequiredArgsConstructor
public class LogoProxyController {
    
    private final RestTemplate restTemplate;
    
    @Value("${app.services.onboarding-service.url:http://localhost:8001}")
    private String onboardingServiceUrl;
    
    /**
     * Upload company logo - proxy to onboarding service
     */
    @PostMapping("/{tenantId}/logo")
//    @PreAuthorize("hasAuthority('SCOPE_tenant:write')")
    public ResponseEntity<Map<String, Object>> uploadLogo(
            @PathVariable String tenantId,
            @RequestParam("file") MultipartFile file) {
        
        log.info("Proxying logo upload request for tenant: {}", tenantId);
        
        try {
            // Prepare multipart request for onboarding service
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.MULTIPART_FORM_DATA);
            
            MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
            body.add("file", new MultipartInputStreamFileResource(file));
            
            HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);
            
            // Forward request to onboarding service
            String url = onboardingServiceUrl + "/api/v1/logos/" + tenantId + "/upload";
            
            @SuppressWarnings("rawtypes")
            ResponseEntity<Map> response = restTemplate.postForEntity(url, requestEntity, Map.class);
            
            log.info("Logo upload proxied successfully for tenant: {}", tenantId);
            
            @SuppressWarnings("unchecked")
            Map<String, Object> responseBody = response.getBody();
            return ResponseEntity.status(response.getStatusCode()).body(responseBody);
            
        } catch (Exception e) {
            log.error("Failed to proxy logo upload for tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("error", "Failed to upload logo"));
        }
    }
    
    /**
     * Get company logo information - proxy to onboarding service
     */
    @GetMapping("/{tenantId}/logo")
//    @PreAuthorize("hasAuthority('SCOPE_tenant:read')")
    public ResponseEntity<Map<String, Object>> getLogoInfo(@PathVariable String tenantId) {
        log.info("Proxying logo info request for tenant: {}", tenantId);
        
        try {
            String url = onboardingServiceUrl + "/api/v1/logos/" + tenantId;
            
            @SuppressWarnings("rawtypes")
            ResponseEntity<Map> response = restTemplate.getForEntity(url, Map.class);
            
            log.debug("Logo info proxied successfully for tenant: {}", tenantId);
            
            @SuppressWarnings("unchecked")
            Map<String, Object> responseBody = response.getBody();
            return ResponseEntity.status(response.getStatusCode()).body(responseBody);
            
        } catch (Exception e) {
            log.error("Failed to proxy logo info for tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("error", "Failed to get logo information"));
        }
    }
    
    /**
     * Delete company logo - proxy to onboarding service
     */
    @DeleteMapping("/{tenantId}/logo")
//    @PreAuthorize("hasAuthority('SCOPE_tenant:write')")
    public ResponseEntity<Map<String, Object>> deleteLogo(@PathVariable String tenantId) {
        log.info("Proxying logo delete request for tenant: {}", tenantId);
        
        try {
            String url = onboardingServiceUrl + "/api/v1/logos/" + tenantId;
            restTemplate.delete(url);
            
            log.info("Logo delete proxied successfully for tenant: {}", tenantId);
            return ResponseEntity.ok(Map.of(
                "message", "Logo deleted successfully",
                "tenant_id", tenantId
            ));
            
        } catch (Exception e) {
            log.error("Failed to proxy logo delete for tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("error", "Failed to delete logo"));
        }
    }
    
    /**
     * Download logo file - proxy to onboarding service
     */
    @GetMapping("/{tenantId}/logo/download")
//    @PreAuthorize("hasAuthority('SCOPE_tenant:read')")
    public ResponseEntity<InputStreamResource> downloadLogo(@PathVariable String tenantId) {
        log.info("Proxying logo download request for tenant: {}", tenantId);
        
        try {
            String url = onboardingServiceUrl + "/api/v1/logos/" + tenantId + "/download";
            ResponseEntity<byte[]> response = restTemplate.getForEntity(url, byte[].class);
            
            if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
                InputStreamResource resource = new InputStreamResource(
                    new ByteArrayInputStream(response.getBody())
                );
                
                HttpHeaders headers = new HttpHeaders();
                headers.setContentType(MediaType.APPLICATION_OCTET_STREAM);
                headers.setContentDisposition(
                    ContentDisposition.attachment().filename("logo").build()
                );
                
                log.debug("Logo download proxied successfully for tenant: {}", tenantId);
                return ResponseEntity.ok()
                        .headers(headers)
                        .body(resource);
            } else {
                return ResponseEntity.notFound().build();
            }
            
        } catch (Exception e) {
            log.error("Failed to proxy logo download for tenant: {}", tenantId, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).build();
        }
    }
    
    /**
     * Public logo endpoint - proxy to onboarding service (no authentication)
     */
    @GetMapping("/public/logos/{tenantId}")
    public ResponseEntity<InputStreamResource> getPublicLogo(@PathVariable String tenantId) {
        log.info("Proxying public logo request for tenant: {}", tenantId);
        
        try {
            String url = onboardingServiceUrl + "/api/v1/public/logos/" + tenantId;
            ResponseEntity<byte[]> response = restTemplate.getForEntity(url, byte[].class);
            
            if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
                InputStreamResource resource = new InputStreamResource(
                    new ByteArrayInputStream(response.getBody())
                );
                
                // Copy content type from original response if available
                MediaType contentType = response.getHeaders().getContentType();
                if (contentType == null) {
                    contentType = MediaType.IMAGE_JPEG; // Default fallback
                }
                
                HttpHeaders headers = new HttpHeaders();
                headers.setContentType(contentType);
                headers.setCacheControl("public, max-age=3600"); // Cache for 1 hour
                
                log.debug("Public logo proxied successfully for tenant: {}", tenantId);
                return ResponseEntity.ok()
                        .headers(headers)
                        .body(resource);
            } else {
                return ResponseEntity.notFound().build();
            }
            
        } catch (Exception e) {
            log.error("Failed to proxy public logo for tenant: {}", tenantId, e);
            return ResponseEntity.notFound().build(); // Return 404 for public endpoint
        }
    }
    
    /**
     * Helper class for multipart file handling in RestTemplate
     */
    private static class MultipartInputStreamFileResource extends InputStreamResource {
        private final String filename;
        
        public MultipartInputStreamFileResource(MultipartFile file) throws Exception {
            super(file.getInputStream());
            this.filename = file.getOriginalFilename();
        }
        
        @Override
        public String getFilename() {
            return this.filename;
        }
        
        @Override
        public long contentLength() {
            return -1; // Unknown length
        }
    }
}
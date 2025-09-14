package io.factorialsystems.authorizationserver2.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;
import org.springframework.http.client.SimpleClientHttpRequestFactory;

/**
 * General application configuration
 * 
 * Note: While WebClient is the recommended replacement for RestTemplate,
 * we're using RestTemplate here as it's more appropriate for traditional 
 * servlet-based Spring Boot applications without WebFlux dependencies.
 */
@Configuration
public class ApplicationConfig {
    
    /**
     * RestTemplate bean for making HTTP requests to other services
     * Configured with appropriate timeout settings
     */
    @Bean
    public RestTemplate restTemplate() {
        SimpleClientHttpRequestFactory factory = new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(30000); // 30 seconds
        factory.setReadTimeout(60000);    // 60 seconds
        
        return new RestTemplate(factory);
    }
}
package io.factorialsystems.authorizationserver2.config;

import lombok.Getter;
import lombok.Setter;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

import java.util.List;

@Getter
@Setter
@Component
@ConfigurationProperties(prefix = "authorization.config.security")
public class AuthorizationProperties {
    private String location;
    private List<String> allowedOrigins;
}

package io.factorialsystems.authorizationserver2.config;

import io.factorialsystems.authorizationserver2.model.Role;
import io.factorialsystems.authorizationserver2.security.CustomAuthenticationFailureHandler;
import io.factorialsystems.authorizationserver2.service.DatabaseUserDetailsService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.WebSecurityCustomizer;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.server.authorization.OAuth2TokenType;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configuration.OAuth2AuthorizationServerConfiguration;
import org.springframework.security.oauth2.server.authorization.config.annotation.web.configurers.OAuth2AuthorizationServerConfigurer;
import org.springframework.security.oauth2.server.authorization.settings.AuthorizationServerSettings;
import org.springframework.security.oauth2.server.authorization.token.JwtEncodingContext;
import org.springframework.security.oauth2.server.authorization.token.OAuth2TokenCustomizer;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.LoginUrlAuthenticationEntryPoint;
import org.springframework.security.web.util.matcher.MediaTypeRequestMatcher;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import static org.springframework.security.config.Customizer.withDefaults;

@Slf4j
@Configuration
@RequiredArgsConstructor
public class SecurityConfig {
		
	@Bean 
	@Order(1)
	SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
			throws Exception {
		OAuth2AuthorizationServerConfiguration.applyDefaultSecurity(http);
		http.getConfigurer(OAuth2AuthorizationServerConfigurer.class)
			.oidc(withDefaults());
		http
			.cors(withDefaults()) // Enable CORS for OAuth2 endpoints
			.exceptionHandling((exceptions) -> exceptions
				.defaultAuthenticationEntryPointFor(
					new LoginUrlAuthenticationEntryPoint("/login"),
					new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
				)
			)
			.oauth2ResourceServer((resourceServer) -> resourceServer
				.jwt(withDefaults()));

		return http.build();
	}

	@Bean 
	@Order(2)
	SecurityFilterChain apiSecurityFilterChain(HttpSecurity http) throws Exception {
		http
			.securityMatcher("/api/v1/**") // Only apply this chain to API endpoints
			.cors(withDefaults()) // Enable CORS for API endpoints
			.csrf(AbstractHttpConfigurer::disable) // Disable CSRF for API endpoints
			.authorizeHttpRequests((authorize) -> authorize
				.requestMatchers("/api/v1/tenants/lookup-by-api-key").permitAll() // Public tenant lookup for chat widget
				.anyRequest().authenticated() // All other API endpoints require authentication
			)
			.oauth2ResourceServer((resourceServer) -> resourceServer
				.jwt(withDefaults()) // Use JWT for API authentication
			)
			.exceptionHandling((exceptions) -> exceptions
				.authenticationEntryPoint((request, response, authException) -> {
					// Return 401 for API endpoints instead of redirecting to login
					response.setStatus(401);
					response.setContentType("application/json");
					response.getWriter().write("{\"error\":\"Unauthorized\",\"message\":\"" + authException.getMessage() + "\"}");
				})
			);
		return http.build();
	}

	@Bean
	@Order(3)
	SecurityFilterChain defaultSecurityFilterChain(
			HttpSecurity http,
			AuthenticationManager authenticationManager,
			CustomAuthenticationFailureHandler customAuthenticationFailureHandler)
			throws Exception {
		http
			.cors(withDefaults()) // Enable CORS for default endpoints
			.authorizeHttpRequests((authorize) -> authorize
				.requestMatchers("/error", "/login", "/register", "/resend-verification", "/verify-email", "/verify-email-test-success", "/verify-email-test-failure", "/verify-email-test-fallback", "/verification-status", "/js/**", "/css/**", "/image/**", "/images/**", "/webjars/**", "/favicon.ico").permitAll()
				.anyRequest().authenticated())
			.authenticationManager(authenticationManager) // Use configured AuthenticationManager
			.formLogin(formLogin -> formLogin
				.loginPage("/login")
				.failureHandler(customAuthenticationFailureHandler) // Use custom failure handler
				.permitAll()
			);
		return http.build();
	}
	
	@Bean
    WebSecurityCustomizer webSecurityCustomizer() {
        return (web) -> web.debug(false)
                .ignoring()
                .requestMatchers("/webjars/**", "/image/**", "/images/**", "/css/**", "/assets/**", "/favicon.ico");
    }

    @Bean
    public PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    public AuthenticationManager authenticationManager(
            UserDetailsService userDetailsService,
            PasswordEncoder passwordEncoder) {
        DaoAuthenticationProvider authenticationProvider = new DaoAuthenticationProvider();
        authenticationProvider.setUserDetailsService(userDetailsService);
        authenticationProvider.setPasswordEncoder(passwordEncoder);

        log.info("Configured AuthenticationManager with DatabaseUserDetailsService and DelegatingPasswordEncoder");

        return new ProviderManager(authenticationProvider);
    }

    @Bean
    public CorsConfigurationSource corsConfigurationSource(AuthorizationProperties authorizationProperties) {
        log.info("Configuring CORS for authorization server");

        CorsConfiguration configuration = new CorsConfiguration();
        
        // Allow requests from frontend and gateway
        configuration.setAllowedOriginPatterns(authorizationProperties.getAllowedOrigins());
        configuration.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"));
        configuration.setAllowedHeaders(List.of("*"));
        configuration.setExposedHeaders(List.of(
            "Authorization", 
            "Content-Type", 
            "Cache-Control", 
            "X-Requested-With", 
            "x-request-id", 
            "Location", 
            "Content-Disposition"
        ));
        
        configuration.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", configuration); // Apply to all endpoints
        return source;
    }

    @Bean
    public AuthorizationServerSettings authorizationServerSettings(AuthorizationProperties authorizationProperties) {
        return AuthorizationServerSettings.builder()
                .issuer(authorizationProperties.getLocation())
                .build();
    }


    @Bean
	OAuth2TokenCustomizer<JwtEncodingContext> tokenCustomizer() {
		return context -> {
			Authentication principal = context.getPrincipal();
			if (OAuth2TokenType.ACCESS_TOKEN.equals(context.getTokenType())) {
				Set<String> authorities = principal.getAuthorities().stream()
						.map(GrantedAuthority::getAuthority)
						.collect(Collectors.toSet());
				context.getClaims().claim("authorities", authorities);
				
				// Add custom user claims if using our DatabaseUserDetailsService
				if (principal.getPrincipal() instanceof DatabaseUserDetailsService.CustomUserPrincipal userPrincipal) {

                    context.getClaims().claim("user_id", userPrincipal.getUserId());
					context.getClaims().claim("tenant_id", userPrincipal.getTenantId());
					context.getClaims().claim("email", userPrincipal.getEmail());
					context.getClaims().claim("full_name", userPrincipal.getFullName());
                    context.getClaims().claim("api_key", userPrincipal.getApiKey());
					
					log.debug("Enhanced JWT token with user claims for: {}", userPrincipal.getUsername());
				}
			}
		};
	}
}

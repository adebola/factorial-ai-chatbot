package io.factorialsystems.authorizationserver2;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class AuthorizationServer2Application {
    public static void main(String[] args) {
        SpringApplication.run(AuthorizationServer2Application.class, args);
    }
}

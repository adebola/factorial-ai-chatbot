package io.factorialsystems.authorizationserver2.config;

import org.mybatis.spring.annotation.MapperScan;
import org.springframework.context.annotation.Configuration;

@Configuration
@MapperScan("io.factorialsystems.authorizationserver2.mapper")
public class MyBatisConfig {}
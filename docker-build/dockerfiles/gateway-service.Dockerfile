# Multi-stage build for Spring Cloud Gateway Service
# Stage 1: Build stage with Maven
FROM maven:3.9-eclipse-temurin-21 AS builder

# Set working directory
WORKDIR /build

# Copy Maven files for dependency caching
COPY gateway-service/pom.xml .
COPY gateway-service/.mvn .mvn
COPY gateway-service/mvnw .
COPY gateway-service/mvnw.cmd .

# Make mvnw executable
RUN chmod +x ./mvnw

# Download dependencies (cached layer if pom.xml doesn't change)
RUN ./mvnw dependency:go-offline -B || mvn dependency:go-offline -B

# Copy source code
COPY gateway-service/src ./src

# Build the application
RUN ./mvnw clean package -DskipTests || mvn clean package -DskipTests

# Stage 2: Runtime stage with JRE
FROM eclipse-temurin:21-jre-alpine

# Install curl for health checks
RUN apk add --no-cache curl

# Create non-root user for security
RUN addgroup -g 1000 spring && \
    adduser -D -u 1000 -G spring spring

# Set working directory
WORKDIR /app

# Copy JAR from builder stage
COPY --from=builder --chown=spring:spring /build/target/gateway-service-*.jar app.jar

# Create logs directory
RUN mkdir -p /app/logs && chown -R spring:spring /app/logs

# Switch to non-root user
USER spring:spring

# JVM optimizations for containers
ENV JAVA_OPTS="-XX:+UseContainerSupport \
               -XX:MaxRAMPercentage=75.0 \
               -XX:InitialRAMPercentage=50.0 \
               -XX:+UseG1GC \
               -XX:MaxGCPauseMillis=100 \
               -XX:+UseStringDeduplication \
               -Djava.security.egd=file:/dev/./urandom \
               -Dspring.backgroundpreinitializer.ignore=true"

# Expose port (Gateway default)
EXPOSE 8080

# Run the application
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar app.jar"]
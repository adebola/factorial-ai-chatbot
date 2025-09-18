# Multi-stage build for optimization
# Stage 1: Build
FROM maven:3.9-eclipse-temurin-21 AS builder

WORKDIR /build

# Copy Maven files
COPY mvnw .
COPY mvnw.cmd .
COPY .mvn .mvn
COPY pom.xml .

# Make mvnw executable
RUN chmod +x ./mvnw

# Download dependencies
RUN ./mvnw dependency:go-offline -B

# Copy source code
COPY src ./src

# Build the application
RUN ./mvnw clean package -DskipTests

# Stage 2: Runtime
FROM eclipse-temurin:21-jre-alpine

# Install curl for health checks
RUN apk add --no-cache curl

# Create non-root user
RUN addgroup -g 1000 spring && \
    adduser -D -u 1000 -G spring spring

WORKDIR /app

# Copy JAR from builder
COPY --from=builder --chown=spring:spring /build/target/authorization-server2-*.jar app.jar

# Switch to non-root user
USER spring:spring

# Expose the port (Spring Authorization Server uses 9000 by default)
EXPOSE 9000

# Run the jar file
ENTRYPOINT ["java", "-jar", "app.jar"]
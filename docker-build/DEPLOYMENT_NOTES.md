# FactorialBot Deployment Notes

## Docker Compose Files Overview

### 1. `docker-compose-production.yml` (Use This for AWS Lightsail)
**Purpose**: Optimized for production deployment on AWS Lightsail with external nginx

**Key Features**:
- ✅ All services bind to `127.0.0.1` for security (nginx proxies external traffic)
- ✅ Resource limits configured for Lightsail instances
- ✅ Production-ready security settings (passwords required)
- ✅ Health checks only on critical infrastructure
- ✅ Optimized logging (20MB max, 5 files)
- ❌ No monitoring services (saves ~4GB RAM)
- ❌ No admin UIs (pgAdmin, Redis Commander removed)

**Resource Usage**: ~4-5GB RAM total
- PostgreSQL: 1GB
- Redis: 256MB
- MinIO: 512MB
- RabbitMQ: 512MB
- Each app service: 256-512MB

### 2. `docker-compose-monitoring.yml` (Future Kubernetes)
**Purpose**: Full monitoring stack saved for enterprise/Kubernetes deployment

**Includes**:
- ELK Stack (Elasticsearch, Logstash, Kibana)
- Prometheus + Grafana + AlertManager
- Various exporters (node, postgres, redis)
- Flower for Celery monitoring

**Resource Usage**: Additional ~6-8GB RAM
- Elasticsearch alone: 2GB
- Not suitable for Lightsail

### 3. `docker-compose-v2-optimized.yml` (Development)
**Purpose**: Local development with reduced health check noise

## AWS Lightsail Deployment Guide

### Prerequisites
```bash
# Minimum Lightsail instance: 4GB RAM, 2 vCPUs
# Recommended: 8GB RAM, 4 vCPUs
```

### Environment Variables (.env file)
```bash
# REQUIRED - Must be set for production
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=strong_password_here
REDIS_PASSWORD=strong_redis_password
MINIO_ROOT_USER=minio_admin
MINIO_ROOT_PASSWORD=strong_minio_password
RABBITMQ_USER=rabbitmq_admin
RABBITMQ_PASSWORD=strong_rabbitmq_password

# Application secrets
OPENAI_API_KEY=sk-your-openai-key
JWT_SECRET_KEY=generate-strong-secret-key
SECRET_KEY=another-strong-secret

# Payment (if using)
PAYSTACK_SECRET_KEY=your_paystack_key
PAYSTACK_WEBHOOK_SECRET=your_webhook_secret
PAYMENT_CALLBACK_URL=https://yourdomain.com/api/v1/payments/callback

# Docker images
CHAT_SERVICE_IMAGE=your-registry/chat-service:latest
ONBOARDING_SERVICE_IMAGE=your-registry/onboarding-service:latest
AUTH_SERVICE_IMAGE=your-registry/authorization-server:latest
GATEWAY_SERVICE_IMAGE=your-registry/gateway-service:latest

# Performance tuning
WEB_CONCURRENCY=4  # Number of workers per service
```

### Nginx Configuration (on Lightsail host)
```nginx
# /etc/nginx/sites-available/factorialbot
upstream gateway {
    server 127.0.0.1:8080;
}

upstream chat {
    server 127.0.0.1:8000;
}

upstream onboarding {
    server 127.0.0.1:8001;
}

upstream auth {
    server 127.0.0.1:9000;
}

server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Main gateway
    location / {
        proxy_pass http://gateway;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket support for chat
    location /ws {
        proxy_pass http://chat;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # Direct routes (bypassing gateway if needed)
    location /api/chat/ {
        proxy_pass http://chat;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/onboarding/ {
        proxy_pass http://onboarding;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /oauth2/ {
        proxy_pass http://auth;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Deployment Steps

1. **Prepare Lightsail Instance**:
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo apt install docker-compose-plugin

# Install nginx
sudo apt install nginx certbot python3-certbot-nginx

# Add user to docker group
sudo usermod -aG docker ubuntu
```

2. **Setup SSL Certificate**:
```bash
sudo certbot --nginx -d yourdomain.com
```

3. **Deploy Application**:
```bash
# Clone repository
git clone your-repo.git
cd factorialbot/docker-build

# Create .env file
nano .env  # Add all required variables

# Pull images (if using registry)
docker compose -f docker-compose-production.yml pull

# Start services
docker compose -f docker-compose-production.yml up -d

# Check logs
docker compose -f docker-compose-production.yml logs -f
```

4. **Configure nginx**:
```bash
# Copy nginx config
sudo nano /etc/nginx/sites-available/factorialbot
# Add configuration from above

# Enable site
sudo ln -s /etc/nginx/sites-available/factorialbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### Monitoring Without Heavy Services

1. **Use Docker native logging**:
```bash
# View logs
docker compose logs -f service-name

# Check resource usage
docker stats
```

2. **Setup log rotation**:
```bash
# Already configured in docker-compose with:
# max-size: "20m"
# max-file: "5"
```

3. **Use Lightsail monitoring**:
- CPU utilization
- Network transfer
- System status checks

4. **Application health checks**:
```bash
# Check service health
curl http://localhost:8080/actuator/health
curl http://localhost:8000/health
curl http://localhost:8001/health
```

### Backup Strategy

```bash
#!/bin/bash
# backup.sh - Run daily via cron

# Backup PostgreSQL
docker exec factorialbot-postgres pg_dumpall -U $POSTGRES_USER > backup-$(date +%Y%m%d).sql

# Backup MinIO data
docker run --rm \
  -v factorialbot-minio-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/minio-backup-$(date +%Y%m%d).tar.gz /data

# Upload to S3 or external storage
aws s3 cp backup-*.sql s3://your-backup-bucket/
aws s3 cp minio-backup-*.tar.gz s3://your-backup-bucket/
```

### Performance Tuning

1. **PostgreSQL** (`postgres-config/postgresql.conf`):
```conf
shared_buffers = 256MB
effective_cache_size = 1GB
maintenance_work_mem = 64MB
work_mem = 4MB
max_connections = 100
```

2. **Redis** (`redis-config/redis.conf`):
```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
save 900 1
save 300 10
save 60 10000
```

3. **Application Workers**:
```bash
# In .env
WEB_CONCURRENCY=4  # Adjust based on CPU cores
```

### Troubleshooting

1. **Out of Memory**:
```bash
# Check memory usage
docker stats
free -h

# Reduce service limits in docker-compose
# Restart services one by one
docker compose restart service-name
```

2. **High CPU**:
```bash
# Check which service is consuming CPU
docker stats
htop

# Check application logs
docker compose logs service-name --tail=100
```

3. **Connection Issues**:
```bash
# Check if services are running
docker compose ps

# Test internal connectivity
docker exec factorialbot-gateway curl http://chat-service:8000/health

# Check nginx
sudo nginx -t
sudo systemctl status nginx
```

## Future Migration to Kubernetes

When ready for Kubernetes:

1. **Add Monitoring Stack**:
```bash
# Use the monitoring compose file
docker compose -f docker-compose-production.yml \
              -f docker-compose-monitoring.yml up -d
```

2. **Configure Application Logging**:
- Add Elasticsearch client to Python services
- Configure structured logging to ship to Elasticsearch
- Add Prometheus metrics endpoints

3. **Setup Helm Charts**:
- Convert docker-compose to Kubernetes manifests
- Use Helm for templating
- Deploy to EKS/GKE/AKS

4. **Benefits of Kubernetes**:
- Auto-scaling
- Self-healing
- Rolling updates
- Better resource utilization
- Native monitoring integration

## Security Checklist

- [ ] All passwords are strong and unique
- [ ] Services bind to localhost only
- [ ] SSL certificates are valid
- [ ] Firewall configured (only 80/443 open)
- [ ] Regular backups scheduled
- [ ] Log rotation configured
- [ ] No default passwords
- [ ] Environment variables not committed to git
- [ ] Database connections use SSL in production
- [ ] Rate limiting enabled on gateway
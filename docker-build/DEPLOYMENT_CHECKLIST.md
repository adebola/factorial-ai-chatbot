# FactorialBot Production Deployment Checklist

## Pre-Deployment

### 1. AWS Lightsail Instance
- [ ] Instance resized to 8GB RAM / 4 vCPU
- [ ] Static IP attached
- [ ] Security groups configured (ports 22, 80, 443 open)
- [ ] Swap file configured (4GB)
- [ ] System updates applied

### 2. Environment Variables
- [ ] Copy `.env.production.example` to `.env`
- [ ] **CHANGE ALL DEFAULT PASSWORDS**
- [ ] Set strong `POSTGRES_PASSWORD`
- [ ] Set strong `REDIS_PASSWORD`
- [ ] Set strong `MINIO_ROOT_PASSWORD`
- [ ] Set strong `RABBITMQ_PASSWORD`
- [ ] Add valid `OPENAI_API_KEY`
- [ ] Generate strong `JWT_SECRET_KEY` (min 32 chars)
- [ ] Generate strong `SECRET_KEY`
- [ ] Configure Paystack keys if using payments

### 3. Docker Images
- [ ] Build all images using `./build-all-services.sh`
- [ ] Tag images appropriately
- [ ] Push to Docker registry (optional)
- [ ] Verify image names in `.env` match built images

## Deployment Steps

### 1. Initial Setup
```bash
# SSH to instance
ssh -i your-key.pem ubuntu@your-instance-ip

# Create project directory
mkdir -p ~/factorialbot/docker-build
cd ~/factorialbot/docker-build

# Copy files (git clone or scp)
git clone your-repo.git .
```

### 2. Configuration Files
- [ ] Copy production docker-compose: `cp docker-compose-production-optimized.yml docker-compose.yml`
- [ ] Create `.env` file with production values
- [ ] Verify all environment variables are set
- [ ] Check database init scripts in `db-init/` directory

### 3. Pre-flight Checks
```bash
# Verify Docker is installed
docker --version
docker compose version

# Check available resources
free -h
df -h

# Verify images exist or can be pulled
docker compose pull

# Validate compose file
docker compose config
```

### 4. Database Initialization
- [ ] Ensure `db-init/` scripts are in place
- [ ] Scripts should create: `chatbot_db`, `onboard_db`, `auth_db`, `vector_db`
- [ ] Verify pgvector extension will be installed

### 5. Start Services
```bash
# Start infrastructure first
docker compose up -d postgres redis minio rabbitmq

# Wait for them to be healthy
docker compose ps

# Run migrations
docker compose up chat-migration onboarding-migration

# Start application services
docker compose up -d chat-service onboarding-service authorization-server gateway-service
```

### 6. Nginx Configuration
- [ ] Install nginx if not present
- [ ] Configure upstream services
- [ ] Set up SSL with Let's Encrypt
- [ ] Configure WebSocket proxy for chat
- [ ] Test configuration: `nginx -t`
- [ ] Reload nginx: `systemctl reload nginx`

## Post-Deployment Verification

### 1. Service Health Checks
```bash
# Check all containers are running
docker compose ps

# Check service health endpoints
curl http://localhost:8080/actuator/health  # Gateway
curl http://localhost:8000/health           # Chat
curl http://localhost:8001/health           # Onboarding
curl http://localhost:9000/actuator/health  # Auth Server

# Check logs for errors
docker compose logs --tail=50
```

### 2. Database Verification
```bash
# Connect to PostgreSQL
docker exec -it postgres psql -U postgres

# Verify databases exist
\l

# Check pgvector extension
\c vector_db
\dx
```

### 3. Storage Verification
```bash
# Check MinIO is accessible
curl http://localhost:9000/minio/health/live

# Verify buckets can be created
docker exec -it minio mc alias set local http://localhost:9000 minioadmin <password>
docker exec -it minio mc mb local/test-bucket
```

### 4. Authentication Test
```bash
# Try to get a token (adjust credentials)
curl -X POST http://localhost:9000/oauth2/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=password" \
  -d "username=testuser" \
  -d "password=testpass" \
  -d "client_id=frontend-client" \
  -d "client_secret=secret"
```

### 5. Application Functionality
- [ ] Test document upload via API
- [ ] Test WebSocket chat connection
- [ ] Verify vector search works
- [ ] Test authentication flow
- [ ] Check payment integration (if applicable)

## Monitoring Setup

### 1. Basic Monitoring
```bash
# Set up cron job for resource monitoring
*/5 * * * * docker stats --no-stream >> /var/log/docker-stats.log

# Log rotation
cat > /etc/logrotate.d/docker-containers << EOF
/var/lib/docker/containers/*/*.log {
  rotate 7
  daily
  compress
  size=10M
  missingok
  delaycompress
  copytruncate
}
EOF
```

### 2. Backup Configuration
```bash
# Create backup script
cat > ~/backup.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker exec postgres pg_dumpall -U postgres > $BACKUP_DIR/postgres_$DATE.sql

# Backup volumes
for volume in postgres_data minio_data redis_data; do
  docker run --rm -v $volume:/data -v $BACKUP_DIR:/backup \
    alpine tar czf /backup/${volume}_$DATE.tar.gz /data
done

# Keep only last 7 days
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
EOF

chmod +x ~/backup.sh

# Add to crontab
0 2 * * * /home/ubuntu/backup.sh
```

## Troubleshooting

### Common Issues

1. **Out of Memory**
   - Check: `docker stats`
   - Fix: Restart services one by one
   - Prevention: Ensure resource limits are set

2. **Service Won't Start**
   - Check: `docker compose logs service-name`
   - Fix: Verify environment variables
   - Fix: Check dependencies are running

3. **Database Connection Failed**
   - Check: `docker exec -it postgres pg_isready`
   - Fix: Verify credentials in .env
   - Fix: Check network connectivity

4. **High CPU Usage**
   - Check: `htop` or `top`
   - Fix: Check for memory pressure
   - Fix: Review application logs

## Security Checklist

- [ ] All default passwords changed
- [ ] Firewall configured (ufw)
- [ ] SSL certificates installed
- [ ] SSH key-only authentication
- [ ] fail2ban configured
- [ ] Regular security updates scheduled
- [ ] Backup encryption enabled
- [ ] Secrets not in version control

## Performance Optimization

- [ ] PostgreSQL tuned for 8GB RAM
- [ ] Redis memory limits set
- [ ] JVM heap sizes optimized
- [ ] Python workers configured (WEB_CONCURRENCY=2)
- [ ] Docker log rotation configured
- [ ] Swap configured but swappiness=10

## Final Verification

- [ ] All services are running
- [ ] Website is accessible via HTTPS
- [ ] API endpoints respond correctly
- [ ] WebSocket connections work
- [ ] Logs show no critical errors
- [ ] Backups are scheduled
- [ ] Monitoring is active
- [ ] Documentation is updated

## Rollback Plan

If deployment fails:
1. Stop all services: `docker compose down`
2. Restore database backup if needed
3. Revert to previous docker images
4. Check logs for root cause
5. Fix issues and retry

## Support Contacts

- AWS Lightsail Support: [Link]
- Docker Documentation: https://docs.docker.com
- Application Logs: `docker compose logs -f`
- System Logs: `/var/log/syslog`
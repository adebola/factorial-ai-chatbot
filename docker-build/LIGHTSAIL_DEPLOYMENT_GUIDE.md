# AWS Lightsail Deployment Guide for FactorialBot

## Instance Recommendations

### Current Setup Analysis
Your current **2GB RAM, 2 vCPU** instance is **severely undersized** for 8 services.

### Service Resource Requirements

| Service | Min RAM | Recommended RAM | CPU Cores |
|---------|---------|-----------------|-----------|
| PostgreSQL/pgvector | 512MB | 1GB | 0.5-1.0 |
| Redis | 128MB | 256MB | 0.1-0.25 |
| MinIO | 256MB | 512MB | 0.25-0.5 |
| RabbitMQ | 256MB | 512MB | 0.25-0.5 |
| Chat Service | 256MB | 512MB | 0.25-0.5 |
| Onboarding Service | 256MB | 512MB | 0.25-0.5 |
| Authorization Server | 512MB | 1GB | 0.5-0.75 |
| Gateway Service | 256MB | 512MB | 0.25-0.5 |
| **TOTAL** | **2.5GB** | **5GB** | **2.5-4.0** |
| **+ OS/Docker/nginx** | **+1GB** | **+2GB** | **+0.5** |
| **GRAND TOTAL** | **3.5GB** | **7GB** | **3-4** |

## Recommended AWS Lightsail Instances

### 🚫 Not Viable
- **2GB RAM, 2 vCPU** ($10/month) - Current setup, will cause OOM kills
- **4GB RAM, 2 vCPU** ($20/month) - Minimal, expect performance issues

### ✅ Recommended for Test Deployment
**8GB RAM, 4 vCPU, 160GB SSD** ($40/month)
- Comfortable headroom for all services
- Allows for traffic spikes
- Room for debugging/monitoring
- **Use the `docker-compose-production-optimized.yml` file**

### 🎯 Production Ready
**16GB RAM, 4 vCPU, 320GB SSD** ($80/month)
- Full production capacity
- Can add monitoring stack
- Supports moderate traffic
- Room for horizontal scaling

## Instance Setup Instructions

### 1. Create New Lightsail Instance
```bash
# Choose Ubuntu 22.04 LTS (not Bitnami nginx)
# Select 8GB RAM, 4 vCPU instance
# Configure networking: Open ports 22, 80, 443
```

### 2. Initial Server Setup
```bash
# SSH into instance
ssh -i your-key.pem ubuntu@your-instance-ip

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker ubuntu

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Install nginx
sudo apt install nginx certbot python3-certbot-nginx -y

# Configure swap (important for 8GB instance)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Set swappiness for better performance
echo 'vm.swappiness=10' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
```

### 3. System Optimization
```bash
# Docker daemon configuration
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2",
  "metrics-addr": "127.0.0.1:9323",
  "experimental": true
}
EOF

sudo systemctl restart docker

# Kernel parameters for production
sudo tee -a /etc/sysctl.conf <<EOF
# Network optimizations
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 8192
net.ipv4.ip_local_port_range = 1024 65535

# File descriptors
fs.file-max = 2097152

# Memory optimizations
vm.overcommit_memory = 1
EOF

sudo sysctl -p
```

### 4. Deploy Application
```bash
# Create project directory
mkdir -p ~/factorialbot/docker-build
cd ~/factorialbot/docker-build

# Copy your files (via git or scp)
# Assuming git:
git clone your-repo.git .

# Create .env file
nano .env
# Add all required environment variables

# Use the optimized compose file
cp docker-compose-production-optimized.yml docker-compose.yml

# Start services
docker compose up -d

# Monitor startup
docker compose logs -f
```

### 5. Configure nginx
```bash
sudo nano /etc/nginx/sites-available/factorialbot

# Add configuration:
upstream gateway {
    server 127.0.0.1:8080;
    keepalive 32;
}

server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 100M;

    location / {
        proxy_pass http://gateway;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Enable site
sudo ln -s /etc/nginx/sites-available/factorialbot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

## Monitoring & Maintenance

### Resource Monitoring
```bash
# Real-time container stats
docker stats

# System resources
htop
free -h
df -h

# Container health
docker compose ps
docker compose logs --tail=100 service-name

# Service health checks
curl http://localhost:8080/actuator/health  # Gateway
curl http://localhost:8000/health  # Chat
curl http://localhost:8001/health  # Onboarding
curl http://localhost:9000/actuator/health  # Auth
```

### Backup Script
```bash
#!/bin/bash
# backup.sh - Add to cron for daily backups

BACKUP_DIR="/home/ubuntu/backups"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
docker exec factorialbot-postgres pg_dumpall -U postgres > $BACKUP_DIR/postgres_$DATE.sql

# Backup volumes
docker run --rm \
  -v factorialbot-postgres-data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/postgres-data_$DATE.tar.gz /data

docker run --rm \
  -v factorialbot-minio-data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/minio-data_$DATE.tar.gz /data

# Keep only last 7 days
find $BACKUP_DIR -name "*.sql" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete
```

### Performance Tuning Tips

1. **PostgreSQL**: The compose file includes optimized settings for 8GB RAM
2. **Redis**: Limited to 256MB with LRU eviction
3. **Java Services**: JVM heap sizes tuned (Auth: 768MB, Gateway: 384MB)
4. **Python Services**: Using 2 workers per service (WEB_CONCURRENCY=2)
5. **MinIO**: Cache enabled for better performance

### Troubleshooting

#### Out of Memory Issues
```bash
# Check memory usage
docker system df
docker stats --no-stream

# Clean up unused resources
docker system prune -a --volumes

# Restart services one by one
docker compose restart service-name
```

#### Service Won't Start
```bash
# Check logs
docker compose logs service-name --tail=200

# Check dependencies
docker compose ps

# Force recreate
docker compose up -d --force-recreate service-name
```

#### High CPU Usage
```bash
# Identify culprit
docker stats
htop

# Check for memory pressure causing swap
vmstat 1 5

# Restart problematic service
docker compose restart service-name
```

## Migration from 2GB to 8GB Instance

1. **Create snapshot** of current 2GB instance
2. **Create new 8GB instance** from Ubuntu 22.04 image
3. **Setup new instance** following steps above
4. **Copy data**:
   ```bash
   # On old instance - backup data
   docker compose down
   tar -czf backup.tar.gz ./

   # Transfer to new instance
   scp -i key.pem backup.tar.gz ubuntu@new-instance:/home/ubuntu/

   # On new instance - restore
   tar -xzf backup.tar.gz
   docker compose up -d
   ```
5. **Update DNS** to point to new instance
6. **Test thoroughly** before decommissioning old instance

## Cost Optimization

### Current Monthly Costs
- Instance (8GB): $40
- Storage (160GB): Included
- Bandwidth (3TB): Included
- Static IP: $3
- **Total: ~$43/month**

### Future Scaling Options
1. **Vertical**: Upgrade to 16GB instance ($80/month)
2. **Horizontal**: Split services across multiple 4GB instances
3. **Managed Services**: Use RDS for PostgreSQL, ElastiCache for Redis
4. **Container Service**: Migrate to AWS ECS or EKS for better orchestration

## Security Checklist

- [ ] Change all default passwords in .env
- [ ] Configure firewall (ufw) to allow only 22, 80, 443
- [ ] Setup SSL with Let's Encrypt
- [ ] Enable fail2ban for SSH protection
- [ ] Regular security updates: `unattended-upgrades`
- [ ] Backup encryption for sensitive data
- [ ] Monitor logs for suspicious activity
- [ ] Use AWS Systems Manager for patch management
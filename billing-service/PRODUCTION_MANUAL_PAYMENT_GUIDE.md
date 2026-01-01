# Production Manual Payment Guide - Docker Environment

This guide explains how to extend a subscription for offline payments in a Docker-based production environment on EC2.

---

## ⚠️ Prerequisites

1. SSH access to production EC2 instance
2. Database access (via Docker or direct connection)
3. Tenant ID of the client
4. Payment amount and details

---

## 🎯 Recommended Approach: SQL Script (Option 1)

This is the **safest and simplest** approach for Docker environments.

### Step 1: Upload SQL Script to EC2

On your local machine:
```bash
# Upload the SQL script to EC2
scp manual_extend_subscription.sql ec2-user@your-ec2-instance:/tmp/
```

Or copy-paste the content into a file on the EC2 instance.

### Step 2: SSH into EC2

```bash
ssh ec2-user@your-ec2-instance
```

### Step 3: Edit the SQL Script

```bash
cd /tmp
nano manual_extend_subscription.sql
```

**Modify these lines** (around line 20-23):
```sql
\set tenant_id '\'YOUR_TENANT_ID_HERE\''
\set payment_amount 50000.00
\set payment_notes '\'Bank transfer - Ref: TRF-20251231-001\''
\set extension_days 30
```

**Example**:
```sql
\set tenant_id '\'a72627cd-0169-434a-9ce1-a694709e329e\''
\set payment_amount 50000.00
\set payment_notes '\'Bank transfer - Reference: TRF20251231001 - Received 31-Dec-2025\''
\set extension_days 30
```

Save and exit (Ctrl+X, Y, Enter).

### Step 4: Find Database Connection Details

**Option A: Connect via Docker container**
```bash
# Find the database container name
docker ps | grep postgres

# Or check your docker-compose.yml for database service name
cat docker-compose.yml | grep -A 5 postgres
```

**Option B: Direct connection (if database is not in Docker)**
```bash
# Check environment variables or .env file
cat .env | grep DATABASE_URL
```

### Step 5: Execute the SQL Script

**Option A: Via Docker container**
```bash
# Copy script into database container
docker cp /tmp/manual_extend_subscription.sql postgres-container:/tmp/

# Execute script inside container
docker exec -it postgres-container psql -U postgres -d billing_db -f /tmp/manual_extend_subscription.sql
```

**Option B: Direct psql connection**
```bash
# If psql is installed on EC2 host
PGPASSWORD=your_password psql -h localhost -U postgres -d billing_db -f /tmp/manual_extend_subscription.sql

# Or if using DATABASE_URL from .env
psql postgresql://postgres:password@localhost:5432/billing_db -f /tmp/manual_extend_subscription.sql
```

### Step 6: Review Output

The script will show:
- Current subscription details
- Payment record created ✅
- Subscription extended ✅
- Invoice generated ✅
- Audit trail logged ✅
- Final verification summary

**Review carefully** before committing!

### Step 7: Commit or Rollback

If everything looks correct:
```bash
# The script runs in a transaction, so you need to commit manually
# Run this SQL:
docker exec -it postgres-container psql -U postgres -d billing_db -c "COMMIT;"
```

If something looks wrong:
```bash
# Rollback the transaction
docker exec -it postgres-container psql -U postgres -d billing_db -c "ROLLBACK;"
```

---

## 🐍 Alternative: Python Script in Docker (Option 2)

If you prefer using the Python script, you can run it inside the billing-service Docker container.

### Step 1: Upload Python Script to EC2

```bash
scp manual_subscription_extension.py ec2-user@your-ec2-instance:/tmp/
```

### Step 2: SSH into EC2 and Find Billing Service Container

```bash
ssh ec2-user@your-ec2-instance

# Find billing service container
docker ps | grep billing-service

# Or check docker-compose
docker-compose ps billing-service
```

### Step 3: Copy Script into Container

```bash
# Copy script into the running billing-service container
docker cp /tmp/manual_subscription_extension.py billing-service:/app/
```

### Step 4: Execute Script Inside Container

```bash
# Execute the script inside the container
docker exec -it billing-service python /app/manual_subscription_extension.py <tenant_id>

# Example:
docker exec -it billing-service python /app/manual_subscription_extension.py a72627cd-0169-434a-9ce1-a694709e329e
```

The script will prompt you for:
- Payment amount (default: plan cost)
- Payment notes
- Extension days (default: 30)
- Confirmation

### Step 5: Verify

The script will show success message with:
- Payment ID
- Invoice number
- New expiration date
- User email

---

## 🔍 Finding the Tenant ID

If you don't have the tenant ID, run this query:

**Via Docker**:
```bash
docker exec -it postgres-container psql -U postgres -d billing_db -c \
"SELECT t.id, t.name, t.domain, s.status, s.current_period_end
 FROM tenants t
 LEFT JOIN subscriptions s ON t.id = s.tenant_id
 WHERE t.name ILIKE '%company_name%'
    OR t.domain ILIKE '%domain%'
 ORDER BY t.created_at DESC;"
```

Replace `company_name` or `domain` with the client's actual details.

---

## 📧 After Extension

1. **Send confirmation email** to client:
   ```
   Subject: Subscription Payment Confirmed

   Dear [Client Name],

   We have received your bank transfer payment of 50,000 NGN.

   Your Basic subscription has been extended:
   - New period: January 1, 2026 to January 31, 2026
   - Invoice: INV-20251231-XXXX

   Thank you for your payment!
   ```

2. **Update your records**:
   - Note the invoice number
   - Record bank transfer reference
   - Mark as reconciled in accounting system

3. **Verify in production** (optional):
   ```bash
   # Check subscription status
   docker exec -it postgres-container psql -U postgres -d billing_db -c \
   "SELECT status, current_period_end FROM subscriptions WHERE tenant_id = 'TENANT_ID';"

   # Check latest payment
   docker exec -it postgres-container psql -U postgres -d billing_db -c \
   "SELECT id, amount, status, payment_method FROM payments
    WHERE tenant_id = 'TENANT_ID' ORDER BY created_at DESC LIMIT 1;"

   # Check latest invoice
   docker exec -it postgres-container psql -U postgres -d billing_db -c \
   "SELECT invoice_number, total_amount, status FROM invoices
    WHERE tenant_id = 'TENANT_ID' ORDER BY created_at DESC LIMIT 1;"
   ```

---

## 🔒 Security Best Practices

1. **Use secure connection**: Always SSH with keys, not passwords
2. **Clean up**: Delete uploaded scripts after use
   ```bash
   rm /tmp/manual_extend_subscription.sql
   docker exec -it billing-service rm /app/manual_subscription_extension.py
   ```

3. **Audit**: Keep a record of manual interventions
   - Who performed it
   - When
   - For which client
   - Amount and reference

4. **Backup**: Take a database backup before major changes
   ```bash
   docker exec -it postgres-container pg_dump -U postgres billing_db > /tmp/billing_db_backup_$(date +%Y%m%d).sql
   ```

---

## 🚨 Troubleshooting

### Issue: "docker: command not found"
**Solution**: Docker is not in PATH. Try:
```bash
sudo docker ps
# Or find docker location
which docker
```

### Issue: "Permission denied"
**Solution**: Add sudo or check user permissions:
```bash
sudo docker exec -it postgres-container ...
```

### Issue: "No such container"
**Solution**: Find correct container name:
```bash
docker ps -a
docker-compose ps
```

### Issue: "Database connection failed"
**Solution**: Check database is running:
```bash
docker ps | grep postgres
docker logs postgres-container
```

### Issue: "Tenant not found"
**Solution**: Verify tenant ID:
```bash
docker exec -it postgres-container psql -U postgres -d billing_db -c \
"SELECT id, name FROM tenants LIMIT 10;"
```

---

## ✅ Quick Reference Card

### Before Running:
- [ ] Have tenant ID
- [ ] Know payment amount
- [ ] Have bank transfer reference
- [ ] Backup database (optional but recommended)

### After Running:
- [ ] Verify payment created
- [ ] Verify subscription extended
- [ ] Verify invoice generated
- [ ] Send confirmation email to client
- [ ] Update accounting records
- [ ] Clean up scripts from server

---

## 📞 Need Help?

If you encounter issues:
1. Check Docker container logs: `docker logs billing-service`
2. Check database logs: `docker logs postgres-container`
3. Verify environment variables: `docker exec billing-service env | grep DATABASE`
4. Test database connection: `docker exec postgres-container psql -U postgres -d billing_db -c "SELECT 1;"`

---

## Example Full Workflow

```bash
# 1. SSH into EC2
ssh ec2-user@your-ec2-instance

# 2. Create and edit SQL script on server
cat > /tmp/extend_subscription.sql << 'EOF'
-- [Paste the SQL script content here, with your tenant ID and payment details]
EOF

# 3. Execute via Docker
docker cp /tmp/extend_subscription.sql postgres:/tmp/
docker exec -it postgres psql -U postgres -d billing_db -f /tmp/extend_subscription.sql

# 4. If output looks good, commit
docker exec -it postgres psql -U postgres -d billing_db -c "COMMIT;"

# 5. Verify
docker exec -it postgres psql -U postgres -d billing_db -c \
"SELECT status, current_period_end FROM subscriptions WHERE tenant_id = 'YOUR_TENANT_ID';"

# 6. Clean up
rm /tmp/extend_subscription.sql
docker exec -it postgres rm /tmp/extend_subscription.sql

# 7. Send confirmation email to client (via your email system)
```

Done! ✅

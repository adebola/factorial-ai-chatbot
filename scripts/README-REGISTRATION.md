# User Registration Scripts for Live Environment

## Overview

These scripts allow you to register new tenants (organizations) and admin users in the FactorialBot **production/live** environment.

## Available Scripts

### 1. Bash Script (register-user-live.sh)
**Best for:** Quick registration, shell environments, CI/CD pipelines

### 2. Python Script (register-user-live.py)
**Best for:** Better error handling, cross-platform compatibility, programmatic use

## Prerequisites

### For Bash Script
- `curl` installed
- Bash 4.0+ (macOS, Linux)

### For Python Script
- Python 3.7+
- `requests` library: `pip install requests`

## Usage

### Interactive Mode (Recommended)

#### Bash:
```bash
cd backend/scripts
./register-user-live.sh
```

#### Python:
```bash
cd backend/scripts
python register-user-live.py
```

The script will prompt you for:
- Organization name
- Organization domain
- Admin username
- Admin email
- Admin first name
- Admin last name
- Admin password

### Non-Interactive Mode (Environment Variables)

#### Bash:
```bash
export ORG_NAME="Acme Corporation"
export ORG_DOMAIN="acme.com"
export ADMIN_USERNAME="admin"
export ADMIN_EMAIL="admin@acme.com"
export ADMIN_FIRST_NAME="John"
export ADMIN_LAST_NAME="Doe"
export ADMIN_PASSWORD="SecurePass123!"

./register-user-live.sh
```

#### Python:
```bash
export ORG_NAME="Acme Corporation"
export ORG_DOMAIN="acme.com"
export ADMIN_USERNAME="admin"
export ADMIN_EMAIL="admin@acme.com"
export ADMIN_FIRST_NAME="John"
export ADMIN_LAST_NAME="Doe"
export ADMIN_PASSWORD="SecurePass123!"

python register-user-live.py --non-interactive
```

### Command-Line Arguments (Python only)

```bash
python register-user-live.py \
    --org-name "Acme Corporation" \
    --org-domain "acme.com" \
    --admin-username "admin" \
    --admin-email "admin@acme.com" \
    --admin-first-name "John" \
    --admin-last-name "Doe" \
    --admin-password "SecurePass123!"
```

### Custom Server URL

By default, scripts target `https://api.chatcraft.cc`. To use a different server:

#### Bash:
```bash
export AUTH_SERVER_URL="https://staging.chatcraft.cc"
./register-user-live.sh
```

#### Python:
```bash
python register-user-live.py --auth-server-url "https://staging.chatcraft.cc"
```

## Field Requirements

### Organization Information
- **Name**: 2-100 characters (e.g., "Acme Corporation")
- **Domain**: Valid domain format (e.g., "acme.com", "example.org")
  - Must be unique across all tenants
  - No subdomains (use "acme.com", not "www.acme.com")

### Administrator Account
- **Username**: 3-50 characters, alphanumeric + underscore + hyphen
  - Must be unique globally
  - Examples: `admin`, `john_doe`, `j-smith`
- **Email**: Valid email format
  - Must be unique globally
  - Will receive verification email
- **First Name**: 1-50 characters (optional)
- **Last Name**: 1-50 characters (optional)
- **Password**: Minimum 8 characters
  - Recommended: Include uppercase, lowercase, numbers, special characters

## Registration Flow

1. **Submit Registration**
   - Script sends POST request to `/register` endpoint
   - Server validates all fields
   - Creates tenant and admin user

2. **Email Verification**
   - Verification email sent to admin email
   - Contains activation link
   - Must be clicked to activate account

3. **Account Activation**
   - Click link in email
   - Account becomes active
   - Can now login

4. **Login**
   - Go to `https://api.chatcraft.cc/login`
   - Use username/email and password
   - Access FactorialBot dashboard

## Success Response

When registration succeeds, you'll see:

```
============================================
  ✓ Registration Successful!
============================================

Organization 'Acme Corporation' has been registered successfully!

📧 A verification email has been sent to: admin@acme.com
   Please check your inbox and click the verification link to activate your account.

Next Steps:
1. Check email inbox for verification link
2. Click verification link to activate account
3. Login at: https://api.chatcraft.cc/login

Login Credentials:
  Username: admin
  Email: admin@acme.com
  Password: <as provided>

✓ Credentials saved to: registration-acme.com-20250106-143022.txt
```

A credentials file is automatically created with format:
```
registration-{domain}-{timestamp}.txt
```

**⚠️ IMPORTANT:** Keep this file secure and delete after verifying the account!

## Error Responses

### Domain Already Taken
```
❌ Error: Domain 'acme.com' is already registered
```
**Solution:** Use a different domain or contact support if you own this domain.

### Username Already Taken
```
❌ Error: Username 'admin' is already taken
```
**Solution:** Choose a different username.

### Email Already Registered
```
❌ Error: Email 'admin@acme.com' is already registered
```
**Solution:** Use a different email or login with existing account.

### Organization Name Taken
```
❌ Error: Organization name 'Acme Corporation' is already taken
```
**Solution:** Choose a different organization name.

### Connection Error
```
❌ Error: Could not connect to https://api.chatcraft.cc/register
```
**Solution:** Check internet connection and verify server URL.

### Validation Errors
```
❌ Registration failed
Response: {
  "domain": "Please enter a valid domain (e.g., yourcompany.com)",
  "adminEmail": "Please enter a valid email address"
}
```
**Solution:** Fix the invalid fields and try again.

## Examples

### Example 1: Tech Startup
```bash
python register-user-live.py \
    --org-name "TechFlow Inc" \
    --org-domain "techflow.io" \
    --admin-username "john_doe" \
    --admin-email "john@techflow.io" \
    --admin-first-name "John" \
    --admin-last-name "Doe" \
    --admin-password "TechFlow2025!"
```

### Example 2: Consulting Firm
```bash
python register-user-live.py \
    --org-name "Global Consulting Partners" \
    --org-domain "gcp-consulting.com" \
    --admin-username "admin" \
    --admin-email "admin@gcp-consulting.com" \
    --admin-first-name "Sarah" \
    --admin-last-name "Johnson" \
    --admin-password "GCP_Secure2025"
```

### Example 3: University Department
```bash
python register-user-live.py \
    --org-name "Computer Science Department - State University" \
    --org-domain "cs.stateuniversity.edu" \
    --admin-username "cs_admin" \
    --admin-email "admin@cs.stateuniversity.edu" \
    --admin-first-name "Dr. Michael" \
    --admin-last-name "Chen" \
    --admin-password "CSdept2025!"
```

## Security Best Practices

### Password Requirements
- ✅ Minimum 8 characters
- ✅ Mix of uppercase and lowercase
- ✅ Include numbers
- ✅ Include special characters
- ✅ Don't use common words or patterns

### After Registration
1. ✅ Immediately verify email
2. ✅ Securely store credentials
3. ✅ Delete credentials file after verification
4. ✅ Never commit credentials to git
5. ✅ Use password manager for long-term storage

### For Production Use
- Use strong, unique passwords
- Enable 2FA if available
- Regularly rotate passwords
- Monitor account activity
- Use organization email domains

## Troubleshooting

### Script Won't Execute (Bash)
```bash
# Make script executable
chmod +x register-user-live.sh

# Run with bash explicitly
bash register-user-live.sh
```

### Python Import Error
```bash
# Install requests library
pip install requests

# Or use pip3
pip3 install requests
```

### SSL Certificate Errors
If you encounter SSL/TLS errors:

```python
# Python: Add verify=False (NOT recommended for production)
response = requests.post(url, json=payload, verify=False)
```

Better solution: Update your system's CA certificates.

### Timeout Errors
- Check internet connection
- Verify server URL is correct
- Try again (server might be temporarily unavailable)
- Check if firewall is blocking the connection

## Testing Registration

### Test in Staging First
```bash
# Point to staging server
python register-user-live.py \
    --auth-server-url "https://staging.chatcraft.cc" \
    --org-name "Test Org" \
    --org-domain "test-org-$(date +%s).com" \
    ...
```

### Verify Email Delivery
- Check spam/junk folder
- Wait 5-10 minutes for email
- Check email logs on server if needed
- Contact support if no email received

## API Endpoint Details

### Request
```http
POST /register HTTP/1.1
Host: api.chatcraft.cc
Content-Type: application/json

{
  "name": "Acme Corporation",
  "domain": "acme.com",
  "adminUsername": "admin",
  "adminEmail": "admin@acme.com",
  "adminFirstName": "John",
  "adminLastName": "Doe",
  "adminPassword": "SecurePass123!"
}
```

### Success Response
```http
HTTP/1.1 200 OK
Content-Type: text/html

<!DOCTYPE html>
<html>
  <!-- Registration success page -->
</html>
```

Or redirect:
```http
HTTP/1.1 302 Found
Location: /registration-success
```

### Error Response
```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "domain": "A tenant with this domain already exists",
  "adminEmail": "A user with this email already exists"
}
```

## Support

If you encounter issues:

1. **Check this documentation** for common errors
2. **Verify all fields** meet requirements
3. **Check server logs** (if you have access)
4. **Contact support** with:
   - Error message
   - Organization domain
   - Admin email (for verification lookup)
   - Timestamp of registration attempt

## Related Documentation

- Authorization Server: `../authorization-server2/README.md`
- OAuth2 Integration: `../OAUTH2_INTEGRATION.md`
- Tenant Management: `../docs/TENANT_MANAGEMENT.md`
- API Documentation: `https://api.chatcraft.cc/docs`

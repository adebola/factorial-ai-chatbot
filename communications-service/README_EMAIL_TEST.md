# Email Test Script

This directory contains a test script to verify the RabbitMQ → Communications Service → SendGrid email pipeline.

## Test Script: `test_email_sender.py`

### Purpose
Simulates the authorization server sending email verification messages to test the complete email processing pipeline.

### Usage

```bash
# Run interactively (will prompt for email and name)
python test_email_sender.py

# Run with automatic input
echo -e "your.email@example.com\nYour Name" | python test_email_sender.py
```

### What it does
1. **Creates a test email message** in the same format as the authorization server
2. **Double-encodes the JSON** (to match authorization server behavior)
3. **Sends via RabbitMQ** using routing key `email.notification`
4. **Uses same configuration** (exchange: `topic-exchange`, credentials from `.env`)

### Expected Output

**Script Output:**
```
🧪 RabbitMQ Email Test Script
==================================================
Enter recipient email: test@example.com
Enter recipient name: Test User

📧 Creating test email message for: Test User <test@example.com>
📨 Message created:
   Tenant ID: test-tenant
   Subject: Test Email Verification - ChatCraft
   Template: email_verification

🚀 Sending message to RabbitMQ...
Connecting to RabbitMQ: user@localhost:5672
Exchange: topic-exchange
✅ Message sent successfully!
   Routing key: email.notification
   Recipient: test@example.com
   Subject: Test Email Verification - ChatCraft
   Message size: 3010 bytes
📡 Connection closed

✅ Test completed successfully!
```

**Communications Service Logs:**
```
15:42:39 [info] Processing email message: unknown
15:42:40 [info] Message sent message_id=xxx recipient=test@example.com
        subject=Test Email Verification - ChatCraft provider=sendgrid
15:42:40 [info] Email processed successfully: xxx
```

### Requirements
- RabbitMQ must be running (Docker container on port 5672)
- Communications service consumer must be running (`python start_consumer.py`)
- Environment variables must be set in `.env` file
- SendGrid API key must be valid for actual email delivery

### Troubleshooting

**"Connection refused" error:**
- Check if RabbitMQ is running: `lsof -i :5672`
- Verify credentials in `.env` file

**"Message sent but no logs in communications service":**
- Check if consumer is running: `python start_consumer.py`
- Verify routing key bindings in consumer code

**"SendGrid 400 error":**
- Verify SendGrid API key in `.env`
- Check email content format

### Configuration
The script reads configuration from the same `.env` file as the communications service:
- `RABBITMQ_HOST` (default: localhost)
- `RABBITMQ_PORT` (default: 5672)
- `RABBITMQ_USERNAME` (default: user)
- `RABBITMQ_PASSWORD` (default: password)
- `RABBITMQ_EXCHANGE` (default: topic-exchange)
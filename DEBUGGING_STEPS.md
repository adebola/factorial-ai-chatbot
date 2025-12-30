# Debugging Communications Service - No Emails Being Sent

## Problem

Messages are being published to RabbitMQ and consumed, but no emails are being sent and no logs appear.

## Diagnosis Steps

### Step 1: Run Communications Service in Foreground

This will let you see any errors that are happening:

```bash
cd /Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/communications-service

# Run in foreground to see output
uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

Watch for:
- "Starting Communications Service" message
- "Started RabbitMQ consumer thread" message
- Any error messages when processing emails

### Step 2: Send a Test Message

In another terminal, run the billing service test:

```bash
cd /Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/billing-service

./venv/bin/python3 test_invoice_pdf_with_rabbitmq.py
```

### Step 3: Watch Communications Service Output

You should see:
```
INFO - received Email Message to be sent
INFO - Processing email message: <message_id>
INFO - Sending Mail for Tenant <tenant_id>
INFO - Email has 1 attachment(s)
INFO -   - invoice-INV-20251224-0001.pdf (application/pdf)
```

### Step 4: Check for Errors

If you see errors, they might be:

**Error 1: Brevo API Error**
```
ApiException: ...
```
Solution: Check BREVO_API_KEY in .env file

**Error 2: Database Connection Error**
```
OperationalError: could not connect to database
```
Solution: Check DATABASE_URL and that PostgreSQL is running

**Error 3: Import Error**
```
ModuleNotFoundError: No module named '...'
```
Solution: Activate virtual environment or install missing packages

**Error 4: Attachment Processing Error**
```
TypeError: ... attachments ...
```
Solution: This would indicate a bug in the attachment handling code

## Quick Verification Commands

### Check Queue Status
```bash
python3 -c "
import pika
credentials = pika.PlainCredentials('user', 'password')
parameters = pika.ConnectionParameters(host='localhost', port=5672, credentials=credentials)
connection = pika.BlockingConnection(parameters)
channel = connection.channel()
result = channel.queue_declare(queue='email.send', passive=True)
print(f'Messages: {result.method.message_count}')
print(f'Consumers: {result.method.consumer_count}')
connection.close()
"
```

### Check Recent Emails in Database
```bash
PGPASSWORD=password psql -h localhost -U postgres -d communications_db -c \
"SELECT to_email, subject, status, sent_at, created_at
FROM email_messages
WHERE created_at > NOW() - INTERVAL '10 minutes'
ORDER BY created_at DESC LIMIT 5;"
```

## Expected Flow

When working correctly, you should see:

1. Billing service publishes message to RabbitMQ
2. Communications service logs: "received Email Message to be sent"
3. Communications service logs: "Email has X attachment(s)"
4. Communications service logs: attachment filename
5. Email sent via Brevo
6. New record in email_messages table
7. Email delivered to recipient

## Current Issue

Messages are:
- ✅ Being published to RabbitMQ
- ✅ Being consumed (queue count = 0)
- ❌ NOT creating database records
- ❌ NOT sending emails
- ❌ NOT producing any logs

This suggests the consumer thread is silently catching and ignoring errors.

## Solution

Run the service in the foreground (Step 1 above) to see the actual error messages.

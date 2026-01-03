# CRITICAL: How to Restart Communications Service Properly

## The Problem

When you edit `rabbitmq_consumer.py`, uvicorn's `--reload` flag reloads the app code, but it does NOT restart the background consumer thread. The old thread keeps running with the old code!

## Solution: Full Restart Required

### Step 1: Stop ALL uvicorn processes
```bash
pkill -9 -f "uvicorn.*8003"
```

### Step 2: Start Fresh
```bash
cd /Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/communications-service

uvicorn app.main:app --host 0.0.0.0 --port 8003 --reload
```

### Step 3: Verify Startup Logs
You should see:
```
INFO:     Started server process [XXXXX]
INFO:     Waiting for application startup.
INFO - Starting Communications Service version=1.0.0
INFO - Started RabbitMQ consumer thread
INFO:     Application startup complete.
```

### Step 4: Run Test
```bash
cd /Users/adebola/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/billing-service

./venv/bin/python3 test_invoice_pdf_with_rabbitmq.py
```

### Step 5: Watch for Logs
In the communications service terminal, you should NOW see:
```
INFO - received Email Message to be sent
INFO - Processing email message: <uuid>
INFO - Sending Mail for Tenant <tenant_id>
INFO - Sending mail to another@factorialsystems.io
INFO - Email has 1 attachment(s)
INFO -   - invoice-INV-20251224-0001.pdf (application/pdf)
```

## Why This Happens

The consumer runs in a daemon thread:
```python
consumer_thread = threading.Thread(target=start_rabbitmq_consumer, ...)
consumer_thread.daemon = True
consumer_thread.start()
```

When uvicorn reloads code:
- ✅ App code is reloaded
- ❌ Background threads are NOT restarted
- ❌ Old thread keeps running with old code

## When to Restart

You MUST do a full restart (kill + start) when you change:
- `rabbitmq_consumer.py`
- `email_service.py`
- Any service used by the consumer
- `main.py`

Auto-reload works fine for:
- API endpoints
- Models
- Non-threaded code

## Verification

After restart, verify the consumer is actually processing messages:

```bash
# Check queue
python3 -c "
import pika
credentials = pika.PlainCredentials('user', 'password')
parameters = pika.ConnectionParameters(host='localhost', port=5672, credentials=credentials)
connection = pika.BlockingConnection(parameters)
channel = connection.channel()
result = channel.queue_declare(queue='email.send', passive=True)
print(f'Messages: {result.method.message_count}')
connection.close()
"

# Check database
PGPASSWORD=password psql -h localhost -U postgres -d communications_db -c \
"SELECT COUNT(*) FROM email_messages WHERE created_at > NOW() - INTERVAL '5 minutes';"
```

If messages = 0 in queue but no new emails in database, the old thread is still running!

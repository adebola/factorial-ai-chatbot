#!/usr/bin/env python3
"""
Manual test to see what happens when consumer processes a message
"""

import os
import sys
import json

os.environ.setdefault('DATABASE_URL', 'postgresql://postgres:password@localhost:5432/communications_db')
os.environ.setdefault('REDIS_URL', 'redis://localhost:6379/0')
os.environ.setdefault('RABBITMQ_HOST', 'localhost')
os.environ.setdefault('RABBITMQ_PORT', '5672')
os.environ.setdefault('RABBITMQ_USER', 'user')
os.environ.setdefault('RABBITMQ_PASSWORD', 'password')

# Add required environment variables
os.environ.setdefault('BREVO_API_KEY', 'your-api-key')
os.environ.setdefault('BREVO_FROM_EMAIL', 'noreply@chatcraft.com')
os.environ.setdefault('BREVO_FROM_NAME', 'ChatCraft')

from app.services.rabbitmq_consumer import RabbitMQConsumer
import pika

print("Testing RabbitMQ consumer message processing...")
print("="*60)

# Check if there are messages in the queue
credentials = pika.PlainCredentials('user', 'password')
parameters = pika.ConnectionParameters(host='localhost', port=5672, credentials=credentials)
connection = pika.BlockingConnection(parameters)
channel = connection.channel()

result = channel.queue_declare(queue='email.send', passive=True)
print(f"\nQueue status:")
print(f"  Messages waiting: {result.method.message_count}")
print(f"  Active consumers: {result.method.consumer_count}")

if result.method.message_count > 0:
    print(f"\n⚠️  WARNING: There are {result.method.message_count} messages in the queue")
    print("These messages are being consumed but not processed!")

    # Try to peek at a message
    method, properties, body = channel.basic_get(queue='email.send', auto_ack=False)
    if method:
        print(f"\nPeeking at first message:")
        try:
            message_data = json.loads(body.decode())
            print(f"  To: {message_data.get('to_email')}")
            print(f"  Subject: {message_data.get('subject')}")
            print(f"  Has attachments: {message_data.get('attachments') is not None}")
            if message_data.get('attachments'):
                print(f"  Number of attachments: {len(message_data.get('attachments'))}")
                for att in message_data.get('attachments', []):
                    print(f"    - {att.get('filename')}")
        except Exception as e:
            print(f"  Error parsing message: {e}")

        # Put the message back (nack without requeue to put it back)
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
else:
    print("\n✅ Queue is empty - messages are being consumed")

connection.close()

print("\n" + "="*60)
print("Consumer test complete")

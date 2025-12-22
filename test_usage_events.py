#!/usr/bin/env python3
"""
Test script to verify all usage events (chat, document, website) are received by billing service.

This script publishes test messages to the usage.events exchange and verifies they match
the usage.# routing key pattern.
"""

import json
import uuid
from datetime import datetime
import pika
import os

def publish_test_events():
    """Publish test events for all usage types"""

    # RabbitMQ connection
    host = os.environ.get("RABBITMQ_HOST", "localhost")
    port = int(os.environ.get("RABBITMQ_PORT", "5672"))
    user = os.environ.get("RABBITMQ_USER", "user")
    password = os.environ.get("RABBITMQ_PASSWORD", "password")
    vhost = os.environ.get("RABBITMQ_VHOST", "/")

    print(host)
    print(user)
    print(password)

    credentials = pika.PlainCredentials(user, password)
    parameters = pika.ConnectionParameters(
        host=host,
        port=port,
        virtual_host=vhost,
        credentials=credentials
    )

    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()

    # Declare exchange (should already exist)
    channel.exchange_declare(
        exchange='usage.events',
        exchange_type='topic',
        durable=True
    )

    test_tenant_id = 'test-tenant-' + str(uuid.uuid4())[:8]

    # Test events
    events = [
        {
            'routing_key': 'usage.chat.message',
            'event': {
                'event_id': str(uuid.uuid4()),
                'event_type': 'usage.chat.message',
                'tenant_id': test_tenant_id,
                'session_id': 'test-session-123',
                'message_count': 1,
                'timestamp': datetime.utcnow().isoformat()
            }
        },
        {
            'routing_key': 'usage.document.added',
            'event': {
                'event_id': str(uuid.uuid4()),
                'event_type': 'usage.document.added',
                'tenant_id': test_tenant_id,
                'document_id': 'test-doc-123',
                'filename': 'test-document.pdf',
                'file_size': 1024,
                'count': 1,
                'timestamp': datetime.utcnow().isoformat()
            }
        },
        {
            'routing_key': 'usage.document.removed',
            'event': {
                'event_id': str(uuid.uuid4()),
                'event_type': 'usage.document.removed',
                'tenant_id': test_tenant_id,
                'document_id': 'test-doc-123',
                'filename': 'test-document.pdf',
                'count': -1,
                'timestamp': datetime.utcnow().isoformat()
            }
        },
        {
            'routing_key': 'usage.website.added',
            'event': {
                'event_id': str(uuid.uuid4()),
                'event_type': 'usage.website.added',
                'tenant_id': test_tenant_id,
                'website_id': 'test-web-123',
                'url': 'https://example.com',
                'pages_scraped': 10,
                'count': 1,
                'timestamp': datetime.utcnow().isoformat()
            }
        },
        {
            'routing_key': 'usage.website.removed',
            'event': {
                'event_id': str(uuid.uuid4()),
                'event_type': 'usage.website.removed',
                'tenant_id': test_tenant_id,
                'website_id': 'test-web-123',
                'url': 'https://example.com',
                'count': -1,
                'timestamp': datetime.utcnow().isoformat()
            }
        }
    ]

    print(f"\n{'='*80}")
    print(f"Publishing test events to RabbitMQ")
    print(f"Exchange: usage.events")
    print(f"Test Tenant ID: {test_tenant_id}")
    print(f"{'='*80}\n")

    for item in events:
        routing_key = item['routing_key']
        event = item['event']

        channel.basic_publish(
            exchange='usage.events',
            routing_key=routing_key,
            body=json.dumps(event),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type='application/json'
            )
        )

        print(f"✓ Published: {routing_key}")
        print(f"  Event ID: {event['event_id']}")
        print(f"  Event Type: {event['event_type']}")
        print(f"  Tenant ID: {event['tenant_id']}")
        print()

    connection.close()

    print(f"{'='*80}")
    print(f"All test events published successfully!")
    print(f"\nCheck billing service logs for:")
    print(f"  - '🔔 _on_message callback triggered! Routing key: usage.chat.message'")
    print(f"  - '🔔 _on_message callback triggered! Routing key: usage.document.added'")
    print(f"  - '🔔 _on_message callback triggered! Routing key: usage.document.removed'")
    print(f"  - '🔔 _on_message callback triggered! Routing key: usage.website.added'")
    print(f"  - '🔔 _on_message callback triggered! Routing key: usage.website.removed'")
    print(f"  - '✅ Received usage event' for each event type")
    print(f"  - 'Incremented/Decremented documents/websites/chats for tenant {test_tenant_id}'")
    print(f"{'='*80}\n")

if __name__ == '__main__':
    try:
        publish_test_events()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

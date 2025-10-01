#!/usr/bin/env python3
"""
Test script to send a RabbitMQ message to the communications service for email testing.
This script simulates what the authorization server does when sending email verification messages.
"""
import json
import os
import uuid

import pika
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_test_email_message(recipient_email: str = "test@example.com", recipient_name: str = "Test User"):
    """Create a test email message in the same format as the authorization server"""

    verification_token = "test_token_" + str(uuid.uuid4())
    base_url = "http://localhost:9002/auth"
    verification_url = f"{base_url}/verify-email?token={verification_token}"

    html_content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verify Your Email</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
        .header {{ text-align: center; margin-bottom: 30px; }}
        .content {{ background: #f9f9f9; padding: 30px; border-radius: 8px; margin: 20px 0; }}
        .button {{ display: inline-block; background: #007bff; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
        .footer {{ text-align: center; color: #666; font-size: 14px; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>ChatCraft</h1>
    </div>
    <div class="content">
        <h2>Verify Your Email Address</h2>
        <p>Hello {recipient_name},</p>
        <p>Thank you for registering with ChatCraft! To complete your registration, please verify your email address by clicking the button below:</p>
        <p style="text-align: center;">
            <a href="{verification_url}" class="button">Verify Email Address</a>
        </p>
        <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
        <p style="word-break: break-all; color: #666;">{verification_url}</p>
        <p><strong>This verification link will expire in 24 hours.</strong></p>
        <p>If you didn't create an account with ChatCraft, you can safely ignore this email.</p>
    </div>
    <div class="footer">
        <p>&copy; 2024 ChatCraft. All rights reserved.</p>
    </div>
</body>
</html>"""

    text_content = f"""ChatCraft - Verify Your Email Address

Hello {recipient_name},

Thank you for registering with ChatCraft! To complete your registration, please verify your email address by visiting this link:

{verification_url}

This verification link will expire in 24 hours.

If you didn't create an account with ChatCraft, you can safely ignore this email.

Best regards,
The ChatCraft Team
"""

    # Create message in the same format as authorization server sends
    message = {
        "tenantId": "test-tenant",
        "toEmail": recipient_email,
        "toName": recipient_name,
        "subject": "Test Email Verification - ChatCraft",
        "htmlContent": html_content,
        "textContent": text_content,
        "template": {
            "templateId": None,
            "templateName": "email_verification",
            "type": "EMAIL_VERIFICATION"
        },
        "templateData": {
            "firstName": recipient_name.split()[0] if " " in recipient_name else recipient_name,
            "lastName": recipient_name.split()[-1] if " " in recipient_name else "",
            "baseUrl": base_url,
            "verificationUrl": verification_url,
            "email": recipient_email
        }
    }

    return message

def send_rabbitmq_message(message_data: dict):
    """Send message to RabbitMQ using the same configuration as the authorization server"""

    # Get RabbitMQ configuration from environment
    host = os.environ.get("RABBITMQ_HOST", "localhost")
    port = int(os.environ.get("RABBITMQ_PORT", "5672"))
    username = os.environ.get("RABBITMQ_USERNAME", "user")
    password = os.environ.get("RABBITMQ_PASSWORD", "password")
    exchange = os.environ.get("RABBITMQ_EXCHANGE", "topic-exchange")

    print(f"Connecting to RabbitMQ: {username}@{host}:{port}")
    print(f"Exchange: {exchange}")

    # Create connection
    credentials = pika.PlainCredentials(username, password)
    parameters = pika.ConnectionParameters(
        host=host,
        port=port,
        credentials=credentials,
        heartbeat=600,
        blocked_connection_timeout=300
    )

    connection = None
    try:
        connection = pika.BlockingConnection(parameters)
        channel = connection.channel()

        # Declare exchange (same as consumer)
        channel.exchange_declare(
            exchange=exchange,
            exchange_type='topic',
            durable=True
        )

        # Convert message to JSON and double-encode it (like authorization server does)
        message_json = json.dumps(message_data)
        double_encoded_message = json.dumps(message_json)  # Double encoding to match auth server

        # Publish message with routing key "email.notification" (like authorization server)
        routing_key = "email.notification"
        channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=double_encoded_message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
                content_type="application/json"
            )
        )

        print(f"✅ Message sent successfully!")
        print(f"   Routing key: {routing_key}")
        print(f"   Recipient: {message_data['toEmail']}")
        print(f"   Subject: {message_data['subject']}")
        print(f"   Message size: {len(double_encoded_message)} bytes")

        return True

    except Exception as e:
        print(f"❌ Failed to send message: {e}")
        return False

    finally:
        if connection and not connection.is_closed:
            connection.close()
            print("📡 Connection closed")

def main():
    """Main function to run the email test"""
    print("🧪 RabbitMQ Email Test Script")
    print("=" * 50)

    # Get recipient email from user input or use default
    recipient_email = input("Enter recipient email (or press Enter for test@example.com): ").strip()
    if not recipient_email:
        recipient_email = "test@example.com"

    recipient_name = input("Enter recipient name (or press Enter for 'Test User'): ").strip()
    if not recipient_name:
        recipient_name = "Test User"

    print(f"\n📧 Creating test email message for: {recipient_name} <{recipient_email}>")

    # Create test message
    message = create_test_email_message(recipient_email, recipient_name)

    print(f"\n📨 Message created:")
    print(f"   Tenant ID: {message['tenantId']}")
    print(f"   Subject: {message['subject']}")
    print(f"   Template: {message['template']['templateName']}")

    # Send message
    print(f"\n🚀 Sending message to RabbitMQ...")
    success = send_rabbitmq_message(message)

    if success:
        print(f"\n✅ Test completed successfully!")
        print(f"   Check the communications service logs for processing confirmation.")
        print(f"   The email should be sent via SendGrid to: {recipient_email}")
    else:
        print(f"\n❌ Test failed!")
        print(f"   Check RabbitMQ connection and configuration.")

    print(f"\n📋 To monitor the communications service, watch the consumer logs.")

if __name__ == "__main__":
    main()
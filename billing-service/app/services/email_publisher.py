"""
Email publisher for communications-service integration.

This module publishes email messages to RabbitMQ, which are consumed by the
communications-service for actual email delivery via SendGrid. This approach provides:
- Separation of concerns (billing handles logic, comms handles delivery)
- Centralized email tracking and rate limiting
- Better reliability through message queue
"""
import logging
import json
import os
import uuid
from typing import Optional
from datetime import datetime
import pika
from pika.exceptions import AMQPConnectionError

logger = logging.getLogger(__name__)


class EmailPublisher:
    """
    Publishes email messages to RabbitMQ for communications-service to process.

    Message format (compatible with communications-service consumer):
    {
        "tenant_id": "...",
        "to_email": "user@example.com",
        "to_name": "John Doe",
        "subject": "Email subject",
        "html_content": "<html>...</html>",
        "text_content": "Plain text...",
        "message_id": "uuid",
        "queued_at": "2025-11-17T20:00:00Z"
    }

    Routing:
        Exchange: communications-exchange (topic)
        Routing Key: email.send
    """

    def __init__(self):
        """Initialize email publisher with RabbitMQ connection settings."""
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USERNAME", "guest")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost = os.environ.get("RABBITMQ_VHOST", "/")

        # Use the same exchange as communications-service
        self.email_exchange = os.environ.get("RABBITMQ_EXCHANGE", "communications-exchange")
        self.email_routing_key = "email.send"

        self.connection = None
        self.channel = None

        logger.info("Email publisher initialized")

    def _connect(self) -> bool:
        """
        Establish connection to RabbitMQ.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Force close any stale connections to prevent EOF errors
            if self.connection:
                try:
                    if not self.connection.is_closed:
                        # Connection exists and is open
                        return True
                    # Connection exists but is closed, clean it up
                    self.connection.close()
                except Exception as e:
                    logger.warning(f"Error checking/closing stale connection: {e}")
                finally:
                    # Always reset connection objects when reconnecting
                    self.connection = None
                    self.channel = None

            # Create new connection
            credentials = pika.PlainCredentials(
                self.rabbitmq_user,
                self.rabbitmq_password
            )
            parameters = pika.ConnectionParameters(
                host=self.rabbitmq_host,
                port=self.rabbitmq_port,
                virtual_host=self.rabbitmq_vhost,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # Declare email exchange (idempotent)
            self.channel.exchange_declare(
                exchange=self.email_exchange,
                exchange_type="topic",
                durable=True
            )

            logger.info(
                f"✅ Connected to RabbitMQ email publisher: {self.rabbitmq_host}:{self.rabbitmq_port}"
            )
            return True

        except AMQPConnectionError as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            self.connection = None
            self.channel = None
            return False

        except Exception as e:
            logger.error(f"Unexpected error connecting to RabbitMQ: {e}", exc_info=True)
            self.connection = None
            self.channel = None
            return False

    def publish_email(
        self,
        tenant_id: str,
        to_email: str,
        subject: str,
        html_content: str,
        to_name: Optional[str] = None,
        text_content: Optional[str] = None
    ) -> bool:
        """
        Publish email message to RabbitMQ for communications-service.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email address
            subject: Email subject
            html_content: HTML email content
            to_name: Recipient name (optional)
            text_content: Plain text content (optional)

        Returns:
            bool: True if published successfully, False otherwise
        """
        try:
            # Ensure connection
            if not self._connect():
                logger.error("Cannot publish email: RabbitMQ connection failed")
                return False

            # Build email message in communications-service format
            message = {
                "tenant_id": tenant_id,
                "to_email": to_email,
                "subject": subject,
                "html_content": html_content,
                "message_id": str(uuid.uuid4()),
                "queued_at": datetime.utcnow().isoformat()
            }

            # Add optional fields
            if to_name:
                message["to_name"] = to_name
            if text_content:
                message["text_content"] = text_content

            # Publish to communications exchange
            self.channel.basic_publish(
                exchange=self.email_exchange,
                routing_key=self.email_routing_key,
                body=json.dumps(message),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # Persistent message
                    content_type="application/json"
                )
            )

            logger.info(
                f"📧 Published email to communications-service: {subject}",
                extra={
                    "tenant_id": tenant_id,
                    "recipient": to_email,
                    "subject": subject
                }
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to publish email: {e}",
                extra={
                    "tenant_id": tenant_id,
                    "recipient": to_email
                },
                exc_info=True
            )
            return False

    def publish_trial_expiring_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        days_remaining: int = 3
    ) -> bool:
        """
        Publish trial expiring notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            days_remaining: Days until trial expires

        Returns:
            bool: True if published successfully
        """
        subject = f"Your ChatCraft Trial Expires in {days_remaining} Days"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Hello {to_name},</h2>
            <p>Your ChatCraft trial period will expire in <strong>{days_remaining} days</strong>.</p>
            <p>To continue using ChatCraft without interruption, please upgrade your subscription.</p>
            <p>If you have any questions, please don't hesitate to contact our support team.</p>
            <p>Best regards,<br>The ChatCraft Team</p>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft trial period will expire in {days_remaining} days.\n\nTo continue using ChatCraft without interruption, please upgrade your subscription.\n\nIf you have any questions, please don't hesitate to contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_trial_expired_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str
    ) -> bool:
        """
        Publish trial expired notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name

        Returns:
            bool: True if published successfully
        """
        subject = "Your ChatCraft Trial Has Expired"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Hello {to_name},</h2>
            <p>Your ChatCraft trial period has expired.</p>
            <p>To continue using ChatCraft, please upgrade to a paid subscription.</p>
            <p>If you have any questions or need assistance, please contact our support team.</p>
            <p>Best regards,<br>The ChatCraft Team</p>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft trial period has expired.\n\nTo continue using ChatCraft, please upgrade to a paid subscription.\n\nIf you have any questions or need assistance, please contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_subscription_expiring_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        plan_name: str,
        days_remaining: int = 7
    ) -> bool:
        """
        Publish subscription expiring notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            plan_name: Name of the subscription plan
            days_remaining: Days until subscription expires

        Returns:
            bool: True if published successfully
        """
        subject = f"Your ChatCraft {plan_name} Subscription Expires in {days_remaining} Days"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Hello {to_name},</h2>
            <p>Your ChatCraft <strong>{plan_name}</strong> subscription will expire in <strong>{days_remaining} days</strong>.</p>
            <p>To continue enjoying uninterrupted service, please renew your subscription.</p>
            <p>If you have any questions, please don't hesitate to contact our support team.</p>
            <p>Best regards,<br>The ChatCraft Team</p>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft {plan_name} subscription will expire in {days_remaining} days.\n\nTo continue enjoying uninterrupted service, please renew your subscription.\n\nIf you have any questions, please don't hesitate to contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_subscription_expired_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        plan_name: str
    ) -> bool:
        """
        Publish subscription expired notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            plan_name: Name of the subscription plan

        Returns:
            bool: True if published successfully
        """
        subject = f"Your ChatCraft {plan_name} Subscription Has Expired"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Hello {to_name},</h2>
            <p>Your ChatCraft <strong>{plan_name}</strong> subscription has expired.</p>
            <p>To restore access to your account, please renew your subscription.</p>
            <p>If you have any questions or need assistance, please contact our support team.</p>
            <p>Best regards,<br>The ChatCraft Team</p>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft {plan_name} subscription has expired.\n\nTo restore access to your account, please renew your subscription.\n\nIf you have any questions or need assistance, please contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_payment_successful_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        plan_name: str,
        amount: float,
        currency: str = "NGN"
    ) -> bool:
        """
        Publish payment successful notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            plan_name: Name of the subscription plan
            amount: Payment amount
            currency: Currency code (default: NGN)

        Returns:
            bool: True if published successfully
        """
        # Format amount based on currency
        if currency == "NGN":
            formatted_amount = f"₦{amount:,.2f}"
        elif currency == "USD":
            formatted_amount = f"${amount:,.2f}"
        else:
            formatted_amount = f"{amount:,.2f} {currency}"

        subject = "Payment Successful - ChatCraft Subscription"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Hello {to_name},</h2>
            <p>Thank you for your payment!</p>
            <p>We have successfully received your payment of <strong>{formatted_amount}</strong> for your <strong>{plan_name}</strong> subscription.</p>
            <p>Your subscription is now active and you can continue using ChatCraft without interruption.</p>
            <p>If you have any questions, please don't hesitate to contact our support team.</p>
            <p>Best regards,<br>The ChatCraft Team</p>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nThank you for your payment!\n\nWe have successfully received your payment of {formatted_amount} for your {plan_name} subscription.\n\nYour subscription is now active and you can continue using ChatCraft without interruption.\n\nIf you have any questions, please don't hesitate to contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_subscription_renewed_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        plan_name: str
    ) -> bool:
        """
        Publish subscription renewed notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            plan_name: Name of the subscription plan

        Returns:
            bool: True if published successfully
        """
        subject = f"Your ChatCraft {plan_name} Subscription Has Been Renewed"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Hello {to_name},</h2>
            <p>Great news! Your ChatCraft <strong>{plan_name}</strong> subscription has been successfully renewed.</p>
            <p>You can continue enjoying all the features and benefits of your subscription without interruption.</p>
            <p>Thank you for being a valued ChatCraft customer!</p>
            <p>Best regards,<br>The ChatCraft Team</p>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nGreat news! Your ChatCraft {plan_name} subscription has been successfully renewed.\n\nYou can continue enjoying all the features and benefits of your subscription without interruption.\n\nThank you for being a valued ChatCraft customer!\n\nBest regards,\nThe ChatCraft Team"

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def close(self):
        """Close RabbitMQ connection."""
        if self.connection and not self.connection.is_closed:
            self.connection.close()
            logger.info("Email publisher connection closed")


# Global instance
email_publisher = EmailPublisher()

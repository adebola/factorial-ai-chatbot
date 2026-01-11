"""
Email publisher for communications-service integration.

MIGRATED TO AIO-PIKA: Now uses async-native RabbitMQ operations with automatic reconnection.
"""
import logging
import json
import os
import uuid
from typing import Optional
from datetime import datetime, timezone

from aio_pika import connect_robust, Message, ExchangeType, DeliveryMode
from aio_pika.abc import AbstractRobustConnection
from aio_pika.exceptions import AMQPException

from ..utils.logo_utils import get_logo_data_url

logger = logging.getLogger(__name__)


class EmailPublisher:
    """Async-native email publisher using aio-pika with automatic reconnection."""

    def __init__(self):
        """Initialize the email publisher with RabbitMQ connection settings."""
        self.rabbitmq_host = os.environ.get("RABBITMQ_HOST", "localhost")
        self.rabbitmq_port = int(os.environ.get("RABBITMQ_PORT", "5672"))
        self.rabbitmq_user = os.environ.get("RABBITMQ_USER", "guest")
        self.rabbitmq_password = os.environ.get("RABBITMQ_PASSWORD", "guest")
        self.rabbitmq_vhost = os.environ.get("RABBITMQ_VHOST", "/")

        self.email_exchange = os.environ.get("RABBITMQ_EXCHANGE", "communications-exchange")
        self.email_routing_key = "email.send"

        self.connection: Optional[AbstractRobustConnection] = None

        logger.info("Email publisher initialized (aio-pika)")

    async def connect(self):
        """Establish robust connection with automatic reconnection."""
        if self.connection and not self.connection.is_closed:
            return

        self.connection = await connect_robust(
            host=self.rabbitmq_host,
            port=self.rabbitmq_port,
            login=self.rabbitmq_user,
            password=self.rabbitmq_password,
            virtualhost=self.rabbitmq_vhost,
            reconnect_interval=1.0,
        )

        logger.info(f"Connected to RabbitMQ at {self.rabbitmq_host}:{self.rabbitmq_port}")

    async def publish_email(
        self,
        tenant_id: str,
        to_email: str,
        subject: str,
        html_content: str,
        to_name: Optional[str] = None,
        text_content: Optional[str] = None,
        attachments: Optional[list] = None
    ) -> bool:
        """Publish email message (pure async, no blocking)."""
        try:
            await self.connect()

            message_data = {
                "tenant_id": tenant_id,
                "to_email": to_email,
                "subject": subject,
                "html_content": html_content,
                "message_id": str(uuid.uuid4()),
                "queued_at": datetime.now(timezone.utc).isoformat()
            }

            if to_name:
                message_data["to_name"] = to_name
            if text_content:
                message_data["text_content"] = text_content
            if attachments:
                message_data["attachments"] = attachments

            async with self.connection.channel() as channel:
                exchange = await channel.declare_exchange(
                    self.email_exchange,
                    ExchangeType.TOPIC,
                    durable=True
                )

                message = Message(
                    body=json.dumps(message_data).encode(),
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    message_id=message_data["message_id"]
                )

                await exchange.publish(message, routing_key=self.email_routing_key)

            logger.info(f"📧 Email published: {subject}", extra={"tenant_id": tenant_id})
            return True

        except Exception as e:
            logger.error(f"Failed to publish email: {e}", exc_info=True)
            return False

    async def close(self):
        """Close connection gracefully."""
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("Email publisher closed")

    async def publish_trial_expiring_email(
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

        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%); padding: 30px; text-align: center; position: relative;">
                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                    <h1 style="color: #ffffff; margin: 0; font-size: 28px;">ChatCraft</h1>
                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Trial Expiration Notice</p>
                </div>

                <!-- Body -->
                <div style="padding: 30px;">
                    <p style="font-size: 16px; color: #333; margin-bottom: 20px;">Hello {to_name},</p>

                    <div style="background-color: #FFF3E0; border-left: 4px solid #FF9800; padding: 20px; margin: 20px 0; border-radius: 4px;">
                        <p style="margin: 0; font-size: 16px; color: #E65100;">
                            ⏰ <strong>Your trial period will expire in {days_remaining} days.</strong>
                        </p>
                    </div>

                    <p style="font-size: 16px; color: #333; line-height: 1.6;">
                        To continue using ChatCraft without interruption, please upgrade your subscription before your trial ends.
                    </p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://chatcraft.com/billing/upgrade" style="background-color: #FF9800; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">Upgrade Now</a>
                    </div>

                    <p style="font-size: 14px; color: #666; line-height: 1.6;">
                        If you have any questions, please don't hesitate to contact our support team.
                    </p>

                    <p style="font-size: 16px; color: #333; margin-top: 30px;">
                        Best regards,<br>
                        <strong>The ChatCraft Team</strong>
                    </p>
                </div>

                <!-- Footer -->
                <div style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #e0e0e0;">
                    <p style="margin: 0; font-size: 12px; color: #999;">
                        This is an automated email. Please do not reply.<br>
                        <a href="https://chatcraft.com" style="color: #FF9800; text-decoration: none;">Visit ChatCraft</a> |
                        <a href="mailto:support@chatcraft.com" style="color: #FF9800; text-decoration: none;">Contact Support</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft trial period will expire in {days_remaining} days.\n\nTo continue using ChatCraft without interruption, please upgrade your subscription.\n\nIf you have any questions, please don't hesitate to contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_trial_expired_email(
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

        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #F44336 0%, #D32F2F 100%); padding: 30px; text-align: center; position: relative;">
                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                    <h1 style="color: #ffffff; margin: 0; font-size: 28px;">ChatCraft</h1>
                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Trial Expired</p>
                </div>

                <!-- Body -->
                <div style="padding: 30px;">
                    <p style="font-size: 16px; color: #333; margin-bottom: 20px;">Hello {to_name},</p>

                    <div style="background-color: #FFEBEE; border-left: 4px solid #F44336; padding: 20px; margin: 20px 0; border-radius: 4px;">
                        <p style="margin: 0; font-size: 16px; color: #B71C1C;">
                            ⚠️ <strong>Your trial period has expired.</strong>
                        </p>
                    </div>

                    <p style="font-size: 16px; color: #333; line-height: 1.6;">
                        To continue using ChatCraft and access all features, please upgrade to a paid subscription.
                    </p>

                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://chatcraft.com/billing/upgrade" style="background-color: #F44336; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block; font-weight: bold;">Upgrade Now</a>
                    </div>

                    <p style="font-size: 14px; color: #666; line-height: 1.6;">
                        If you have any questions or need assistance, please contact our support team.
                    </p>

                    <p style="font-size: 16px; color: #333; margin-top: 30px;">
                        Best regards,<br>
                        <strong>The ChatCraft Team</strong>
                    </p>
                </div>

                <!-- Footer -->
                <div style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #e0e0e0;">
                    <p style="margin: 0; font-size: 12px; color: #999;">
                        This is an automated email. Please do not reply.<br>
                        <a href="https://chatcraft.com" style="color: #F44336; text-decoration: none;">Visit ChatCraft</a> |
                        <a href="mailto:support@chatcraft.com" style="color: #F44336; text-decoration: none;">Contact Support</a>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft trial period has expired.\n\nTo continue using ChatCraft, please upgrade to a paid subscription.\n\nIf you have any questions or need assistance, please contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_subscription_expiring_email(
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
        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        subject = f"Your ChatCraft {plan_name} Subscription Expires in {days_remaining} Days"
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Subscription Expiring</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f5f5;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden;">
                            <!-- Header with Logo and Branding -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #1E88E5 0%, #1565C0 100%); padding: 30px; text-align: center; position: relative;">
                                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">ChatCraft</h1>
                                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">{plan_name} Plan</p>
                                </td>
                            </tr>

                            <!-- Main Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="color: #333333; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Hello {to_name},</h2>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Your ChatCraft <strong>{plan_name}</strong> subscription will expire in <strong style="color: #1E88E5;">{days_remaining} days</strong>.
                                    </p>

                                    <!-- Warning Box -->
                                    <div style="background-color: #E3F2FD; border-left: 4px solid #1E88E5; padding: 15px; margin: 20px 0; border-radius: 4px;">
                                        <p style="color: #1565C0; font-size: 14px; line-height: 1.6; margin: 0;">
                                            <strong>Action Required:</strong> To continue enjoying uninterrupted service, please renew your subscription before it expires.
                                        </p>
                                    </div>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        After your subscription expires, you will lose access to:
                                    </p>

                                    <ul style="color: #555555; font-size: 16px; line-height: 1.8; margin: 0 0 20px 0; padding-left: 20px;">
                                        <li>Document and website knowledge base</li>
                                        <li>AI-powered chat responses</li>
                                        <li>All premium features</li>
                                    </ul>

                                    <!-- CTA Button -->
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="https://app.chatcraft.cc/subscriptions" style="background-color: #1E88E5; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block;">
                                            Renew Subscription
                                        </a>
                                    </div>

                                    <p style="color: #555555; font-size: 14px; line-height: 1.6; margin: 20px 0 0 0;">
                                        If you have any questions, please don't hesitate to contact our support team.
                                    </p>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                                    <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0;">
                                        Best regards,<br>
                                        <strong>The ChatCraft Team</strong>
                                    </p>
                                    <p style="color: #999999; font-size: 12px; margin: 15px 0 0 0;">
                                        <a href="https://chatcraft.cc" style="color: #1E88E5; text-decoration: none;">ChatCraft</a> |
                                        <a href="https://chatcraft.cc/support" style="color: #1E88E5; text-decoration: none;">Support</a> |
                                        <a href="https://chatcraft.cc/privacy" style="color: #1E88E5; text-decoration: none;">Privacy Policy</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft {plan_name} subscription will expire in {days_remaining} days.\n\nTo continue enjoying uninterrupted service, please renew your subscription.\n\nIf you have any questions, please don't hesitate to contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_subscription_expired_email(
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
        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        subject = f"Your ChatCraft {plan_name} Subscription Has Expired"
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Subscription Expired</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f5f5;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden;">
                            <!-- Header with Logo and Branding -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #F44336 0%, #D32F2F 100%); padding: 30px; text-align: center; position: relative;">
                                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">ChatCraft</h1>
                                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">{plan_name} Plan</p>
                                </td>
                            </tr>

                            <!-- Main Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="color: #333333; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Hello {to_name},</h2>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Your ChatCraft <strong>{plan_name}</strong> subscription has <strong style="color: #F44336;">expired</strong>.
                                    </p>

                                    <!-- Critical Alert Box -->
                                    <div style="background-color: #FFEBEE; border-left: 4px solid #F44336; padding: 15px; margin: 20px 0; border-radius: 4px;">
                                        <p style="color: #C62828; font-size: 14px; line-height: 1.6; margin: 0;">
                                            <strong>Immediate Action Required:</strong> Your account access has been suspended. Renew your subscription to restore full access.
                                        </p>
                                    </div>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        You currently do not have access to:
                                    </p>

                                    <ul style="color: #555555; font-size: 16px; line-height: 1.8; margin: 0 0 20px 0; padding-left: 20px;">
                                        <li>Document and website knowledge base</li>
                                        <li>AI-powered chat responses</li>
                                        <li>All premium features</li>
                                        <li>Your data and conversation history</li>
                                    </ul>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        Renew now to restore immediate access to all your data and features.
                                    </p>

                                    <!-- CTA Button -->
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="https://app.chatcraft.cc/subscriptions" style="background-color: #F44336; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block;">
                                            Renew Subscription Now
                                        </a>
                                    </div>

                                    <p style="color: #555555; font-size: 14px; line-height: 1.6; margin: 20px 0 0 0;">
                                        If you have any questions or need assistance, please contact our support team.
                                    </p>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                                    <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0;">
                                        Best regards,<br>
                                        <strong>The ChatCraft Team</strong>
                                    </p>
                                    <p style="color: #999999; font-size: 12px; margin: 15px 0 0 0;">
                                        <a href="https://chatcraft.cc" style="color: #F44336; text-decoration: none;">ChatCraft</a> |
                                        <a href="https://chatcraft.cc/support" style="color: #F44336; text-decoration: none;">Support</a> |
                                        <a href="https://chatcraft.cc/privacy" style="color: #F44336; text-decoration: none;">Privacy Policy</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft {plan_name} subscription has expired.\n\nTo restore access to your account, please renew your subscription.\n\nIf you have any questions or need assistance, please contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_payment_successful_email(
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
        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        # Format amount based on currency
        if currency == "NGN":
            formatted_amount = f"₦{amount:,.2f}"
        elif currency == "USD":
            formatted_amount = f"${amount:,.2f}"
        else:
            formatted_amount = f"{amount:,.2f} {currency}"

        subject = "Payment Successful - ChatCraft Subscription"
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Payment Successful</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f5f5;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden;">
                            <!-- Header with Logo and Branding -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #4CAF50 0%, #388E3C 100%); padding: 30px; text-align: center; position: relative;">
                                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">ChatCraft</h1>
                                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Payment Successful</p>
                                </td>
                            </tr>

                            <!-- Main Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="color: #333333; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Hello {to_name},</h2>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Thank you for your payment!
                                    </p>

                                    <!-- Success Box -->
                                    <div style="background-color: #E8F5E9; border-left: 4px solid #4CAF50; padding: 15px; margin: 20px 0; border-radius: 4px;">
                                        <p style="color: #2E7D32; font-size: 14px; line-height: 1.6; margin: 0;">
                                            <strong>Payment Confirmed:</strong> We have successfully received your payment of <strong>{formatted_amount}</strong> for your <strong>{plan_name}</strong> subscription.
                                        </p>
                                    </div>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        Your subscription is now <strong style="color: #4CAF50;">active</strong> and you can continue using ChatCraft without interruption.
                                    </p>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        What you can do now:
                                    </p>

                                    <ul style="color: #555555; font-size: 16px; line-height: 1.8; margin: 0 0 20px 0; padding-left: 20px;">
                                        <li>Upload documents and ingest websites</li>
                                        <li>Chat with your AI-powered knowledge base</li>
                                        <li>Access all premium features</li>
                                        <li>Embed chat widgets on your website</li>
                                    </ul>

                                    <!-- CTA Button -->
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="https://app.chatcraft.cc/dashboard" style="background-color: #4CAF50; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block;">
                                            Go to Dashboard
                                        </a>
                                    </div>

                                    <p style="color: #555555; font-size: 14px; line-height: 1.6; margin: 20px 0 0 0;">
                                        If you have any questions, please don't hesitate to contact our support team.
                                    </p>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                                    <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0;">
                                        Best regards,<br>
                                        <strong>The ChatCraft Team</strong>
                                    </p>
                                    <p style="color: #999999; font-size: 12px; margin: 15px 0 0 0;">
                                        <a href="https://chatcraft.cc" style="color: #4CAF50; text-decoration: none;">ChatCraft</a> |
                                        <a href="https://chatcraft.cc/support" style="color: #4CAF50; text-decoration: none;">Support</a> |
                                        <a href="https://chatcraft.cc/privacy" style="color: #4CAF50; text-decoration: none;">Privacy Policy</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nThank you for your payment!\n\nWe have successfully received your payment of {formatted_amount} for your {plan_name} subscription.\n\nYour subscription is now active and you can continue using ChatCraft without interruption.\n\nIf you have any questions, please don't hesitate to contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_subscription_renewed_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        plan_name: str,
        renewal_amount: Optional[float] = None,
        currency: Optional[str] = None,
        new_period_end: Optional['datetime'] = None,
        payment_reference: Optional[str] = None
    ) -> bool:
        """
        Publish subscription renewed notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            plan_name: Name of the subscription plan
            renewal_amount: Amount charged for renewal (optional)
            currency: Currency code (NGN, USD, etc.) (optional)
            new_period_end: End of new billing period (optional)
            payment_reference: Payment reference for tracking (optional)

        Returns:
            bool: True if published successfully
        """
        # Format amount if provided
        amount_html = ""
        amount_text = ""
        if renewal_amount is not None and currency:
            symbol = "₦" if currency == "NGN" else "$" if currency == "USD" else currency
            amount_html = f"<p>Renewal Amount: <strong>{symbol}{renewal_amount:,.2f}</strong></p>"
            amount_text = f"Renewal Amount: {symbol}{renewal_amount:,.2f}\n"

        # Format billing period if provided
        period_html = ""
        period_text = ""
        if new_period_end:
            period_html = f"<p>Your subscription is now active until <strong>{new_period_end.strftime('%B %d, %Y')}</strong></p>"
            period_text = f"Your subscription is now active until {new_period_end.strftime('%B %d, %Y')}\n"

        # Format reference if provided
        reference_html = ""
        reference_text = ""
        if payment_reference:
            reference_html = f"<p><small>Payment Reference: {payment_reference}</small></p>"
            reference_text = f"\nPayment Reference: {payment_reference}"

        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        subject = f"Your ChatCraft {plan_name} Subscription Has Been Renewed"
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Subscription Renewed</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f5f5;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden;">
                            <!-- Header with Logo and Branding -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #4CAF50 0%, #388E3C 100%); padding: 30px; text-align: center; position: relative;">
                                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">ChatCraft</h1>
                                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">{plan_name} Plan</p>
                                </td>
                            </tr>

                            <!-- Main Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="color: #333333; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Hello {to_name},</h2>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Great news! Your ChatCraft <strong>{plan_name}</strong> subscription has been <strong style="color: #4CAF50;">successfully renewed</strong>.
                                    </p>

                                    <!-- Success Box -->
                                    <div style="background-color: #E8F5E9; border-left: 4px solid #4CAF50; padding: 15px; margin: 20px 0; border-radius: 4px;">
                                        <p style="color: #2E7D32; font-size: 14px; line-height: 1.6; margin: 0;">
                                            <strong>Subscription Renewed:</strong> Your subscription is now active and all features are available.
                                        </p>
                                    </div>

                                    {f'<p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">Renewal Amount: <strong>{("₦" if currency == "NGN" else "$" if currency == "USD" else currency) + f"{renewal_amount:,.2f}"}</strong></p>' if renewal_amount is not None and currency else ''}
                                    {f'<p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">Your subscription is now active until <strong>{new_period_end.strftime("%B %d, %Y")}</strong></p>' if new_period_end else ''}

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        You can continue enjoying all the features and benefits of your subscription without interruption:
                                    </p>

                                    <ul style="color: #555555; font-size: 16px; line-height: 1.8; margin: 0 0 20px 0; padding-left: 20px;">
                                        <li>Unlimited access to your knowledge base</li>
                                        <li>AI-powered chat responses</li>
                                        <li>Document and website ingestion</li>
                                        <li>All premium features</li>
                                    </ul>

                                    {f'<p style="color: #999999; font-size: 12px; line-height: 1.6; margin: 20px 0 0 0;">Payment Reference: {payment_reference}</p>' if payment_reference else ''}

                                    <!-- CTA Button -->
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="https://app.chatcraft.cc/dashboard" style="background-color: #4CAF50; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block;">
                                            Go to Dashboard
                                        </a>
                                    </div>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0 0 0;">
                                        Thank you for being a valued ChatCraft customer!
                                    </p>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                                    <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0;">
                                        Best regards,<br>
                                        <strong>The ChatCraft Team</strong>
                                    </p>
                                    <p style="color: #999999; font-size: 12px; margin: 15px 0 0 0;">
                                        <a href="https://chatcraft.cc" style="color: #4CAF50; text-decoration: none;">ChatCraft</a> |
                                        <a href="https://chatcraft.cc/support" style="color: #4CAF50; text-decoration: none;">Support</a> |
                                        <a href="https://chatcraft.cc/privacy" style="color: #4CAF50; text-decoration: none;">Privacy Policy</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nGreat news! Your ChatCraft {plan_name} subscription has been successfully renewed.\n\n{amount_text}{period_text}\nYou can continue enjoying all the features and benefits of your subscription without interruption.{reference_text}\n\nThank you for being a valued ChatCraft customer!\n\nBest regards,\nThe ChatCraft Team"

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_plan_upgraded_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        old_plan_name: str,
        new_plan_name: str,
        proration_amount: float,
        currency: str = "NGN"
    ) -> bool:
        """
        Publish plan upgraded notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            old_plan_name: Previous plan name
            new_plan_name: New plan name
            proration_amount: Prorated charge amount
            currency: Currency code

        Returns:
            bool: True if published successfully
        """
        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        # Format amount
        if currency == "NGN":
            formatted_amount = f"₦{proration_amount:,.2f}"
        elif currency == "USD":
            formatted_amount = f"${proration_amount:,.2f}"
        else:
            formatted_amount = f"{proration_amount:,.2f} {currency}"

        subject = f"Your ChatCraft Plan Has Been Upgraded to {new_plan_name}"
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Plan Upgraded</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f5f5;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden;">
                            <!-- Header with Logo and Branding -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #673AB7 0%, #512DA8 100%); padding: 30px; text-align: center; position: relative;">
                                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">ChatCraft</h1>
                                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Plan Upgraded</p>
                                </td>
                            </tr>

                            <!-- Main Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="color: #333333; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Hello {to_name},</h2>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Great news! Your ChatCraft subscription has been <strong style="color: #673AB7;">upgraded</strong> from <strong>{old_plan_name}</strong> to <strong>{new_plan_name}</strong>.
                                    </p>

                                    <!-- Success Box -->
                                    <div style="background-color: #EDE7F6; border-left: 4px solid #673AB7; padding: 15px; margin: 20px 0; border-radius: 4px;">
                                        <p style="color: #4527A0; font-size: 14px; line-height: 1.6; margin: 0;">
                                            <strong>Upgrade Complete:</strong> You now have access to all the enhanced features and limits of the {new_plan_name} plan.
                                        </p>
                                    </div>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        A prorated charge of <strong>{formatted_amount}</strong> has been applied for the remaining days in your current billing period.
                                    </p>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        Enhanced features now available:
                                    </p>

                                    <ul style="color: #555555; font-size: 16px; line-height: 1.8; margin: 0 0 20px 0; padding-left: 20px;">
                                        <li>Increased document and website limits</li>
                                        <li>Higher monthly chat capacity</li>
                                        <li>Priority support</li>
                                        <li>Advanced features and capabilities</li>
                                    </ul>

                                    <!-- CTA Button -->
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="https://app.chatcraft.cc/dashboard" style="background-color: #673AB7; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block;">
                                            Explore New Features
                                        </a>
                                    </div>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0 0 0;">
                                        Thank you for choosing ChatCraft!
                                    </p>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                                    <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0;">
                                        Best regards,<br>
                                        <strong>The ChatCraft Team</strong>
                                    </p>
                                    <p style="color: #999999; font-size: 12px; margin: 15px 0 0 0;">
                                        <a href="https://chatcraft.cc" style="color: #673AB7; text-decoration: none;">ChatCraft</a> |
                                        <a href="https://chatcraft.cc/support" style="color: #673AB7; text-decoration: none;">Support</a> |
                                        <a href="https://chatcraft.cc/privacy" style="color: #673AB7; text-decoration: none;">Privacy Policy</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nGreat news! Your ChatCraft subscription has been upgraded from {old_plan_name} to {new_plan_name}.\n\nYou now have access to all the enhanced features and limits of the {new_plan_name} plan.\n\nA prorated charge of {formatted_amount} has been applied for the remaining days in your current billing period.\n\nThank you for choosing ChatCraft!\n\nBest regards,\nThe ChatCraft Team"

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_plan_downgraded_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        old_plan_name: str,
        new_plan_name: str,
        effective_date: 'datetime',
        immediate: bool = False
    ) -> bool:
        """
        Publish plan downgraded notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            old_plan_name: Previous plan name
            new_plan_name: New plan name
            effective_date: When downgrade takes effect
            immediate: Whether downgrade is immediate

        Returns:
            bool: True if published successfully
        """
        from datetime import datetime

        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        formatted_date = effective_date.strftime("%B %d, %Y")

        if immediate:
            subject = f"Your ChatCraft Plan Has Been Changed to {new_plan_name}"
            timing_text = "Your plan has been changed immediately."
        else:
            subject = f"Your ChatCraft Plan Will Change to {new_plan_name} on {formatted_date}"
            timing_text = f"Your plan will change to {new_plan_name} on <strong>{formatted_date}</strong>."

        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Plan Downgraded</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f5f5;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden;">
                            <!-- Header with Logo and Branding -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #607D8B 0%, #455A64 100%); padding: 30px; text-align: center; position: relative;">
                                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">ChatCraft</h1>
                                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Plan Change Notice</p>
                                </td>
                            </tr>

                            <!-- Main Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="color: #333333; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Hello {to_name},</h2>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Your ChatCraft subscription plan is changing from <strong>{old_plan_name}</strong> to <strong>{new_plan_name}</strong>.
                                    </p>

                                    <!-- Info Box -->
                                    <div style="background-color: #ECEFF1; border-left: 4px solid #607D8B; padding: 15px; margin: 20px 0; border-radius: 4px;">
                                        <p style="color: #37474F; font-size: 14px; line-height: 1.6; margin: 0;">
                                            <strong>Plan Change:</strong> {timing_text}
                                        </p>
                                    </div>

                                    {f'<p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">You will continue to have access to all <strong>{old_plan_name}</strong> features until <strong>{formatted_date}</strong>.</p>' if not immediate else ''}

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        Your new plan will include:
                                    </p>

                                    <ul style="color: #555555; font-size: 16px; line-height: 1.8; margin: 0 0 20px 0; padding-left: 20px;">
                                        <li>Access to core ChatCraft features</li>
                                        <li>Adjusted usage limits</li>
                                        <li>Continued support</li>
                                    </ul>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        If you have any questions or would like to keep your current plan, please contact our support team.
                                    </p>

                                    <!-- CTA Button -->
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="https://app.chatcraft.cc/subscriptions" style="background-color: #607D8B; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block;">
                                            View Subscription
                                        </a>
                                    </div>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                                    <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0;">
                                        Best regards,<br>
                                        <strong>The ChatCraft Team</strong>
                                    </p>
                                    <p style="color: #999999; font-size: 12px; margin: 15px 0 0 0;">
                                        <a href="https://chatcraft.cc" style="color: #607D8B; text-decoration: none;">ChatCraft</a> |
                                        <a href="https://chatcraft.cc/support" style="color: #607D8B; text-decoration: none;">Support</a> |
                                        <a href="https://chatcraft.cc/privacy" style="color: #607D8B; text-decoration: none;">Privacy Policy</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft subscription plan is changing from {old_plan_name} to {new_plan_name}.\n\n{timing_text.replace('<strong>', '').replace('</strong>', '')}\n\n{'' if immediate else f'You will continue to have access to all {old_plan_name} features until {formatted_date}.'}If you have any questions or would like to keep your current plan, please contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_subscription_cancelled_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        plan_name: str,
        effective_date: 'datetime',
        immediate: bool = False
    ) -> bool:
        """
        Publish subscription cancelled notification.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            plan_name: Plan being cancelled
            effective_date: When cancellation takes effect
            immediate: Whether cancellation is immediate

        Returns:
            bool: True if published successfully
        """
        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        formatted_date = effective_date.strftime("%B %d, %Y")

        if immediate:
            subject = "Your ChatCraft Subscription Has Been Cancelled"
            timing_text = "Your subscription has been cancelled immediately."
            access_text = ""
        else:
            subject = f"Your ChatCraft Subscription Will Be Cancelled on {formatted_date}"
            timing_text = f"Your subscription will be cancelled on <strong>{formatted_date}</strong>."
            access_text = f"<p>You will continue to have access to all {plan_name} features until {formatted_date}.</p>"

        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Subscription Cancelled</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f5f5;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden;">
                            <!-- Header with Logo and Branding -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #FFA726 0%, #FB8C00 100%); padding: 30px; text-align: center; position: relative;">
                                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">ChatCraft</h1>
                                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Subscription Cancellation</p>
                                </td>
                            </tr>

                            <!-- Main Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="color: #333333; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Hello {to_name},</h2>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        We're sorry to see you go!
                                    </p>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        Your ChatCraft <strong>{plan_name}</strong> subscription is being cancelled.
                                    </p>

                                    <!-- Info Box -->
                                    <div style="background-color: #FFF3E0; border-left: 4px solid #FFA726; padding: 15px; margin: 20px 0; border-radius: 4px;">
                                        <p style="color: #E65100; font-size: 14px; line-height: 1.6; margin: 0;">
                                            <strong>Cancellation Notice:</strong> {timing_text}
                                        </p>
                                    </div>

                                    {f'<p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">You will continue to have access to all <strong>{plan_name}</strong> features until <strong>{formatted_date}</strong>.</p>' if not immediate else ''}

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        If you change your mind or cancelled by mistake, you can reactivate your subscription anytime from your account settings.
                                    </p>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        We'd love to hear your feedback on how we can improve. Please feel free to reach out to our support team.
                                    </p>

                                    <!-- CTA Buttons -->
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="https://app.chatcraft.cc/subscriptions" style="background-color: #FFA726; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block; margin: 0 5px;">
                                            Reactivate Subscription
                                        </a>
                                        <a href="https://chatcraft.cc/support" style="background-color: #607D8B; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block; margin: 0 5px;">
                                            Contact Support
                                        </a>
                                    </div>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                                    <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0;">
                                        Best regards,<br>
                                        <strong>The ChatCraft Team</strong>
                                    </p>
                                    <p style="color: #999999; font-size: 12px; margin: 15px 0 0 0;">
                                        <a href="https://chatcraft.cc" style="color: #FFA726; text-decoration: none;">ChatCraft</a> |
                                        <a href="https://chatcraft.cc/support" style="color: #FFA726; text-decoration: none;">Support</a> |
                                        <a href="https://chatcraft.cc/privacy" style="color: #FFA726; text-decoration: none;">Privacy Policy</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nWe're sorry to see you go!\n\nYour ChatCraft {plan_name} subscription is being cancelled.\n\n{timing_text.replace('<strong>', '').replace('</strong>', '')}\n\n{access_text.replace('<p>', '').replace('</p>', '')}If you change your mind or cancelled by mistake, you can reactivate your subscription anytime from your account settings.\n\nWe'd love to hear your feedback on how we can improve. Please feel free to reach out to our support team.\n\nBest regards,\nThe ChatCraft Team"

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_invoice_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        invoice_number: str,
        total_amount: float,
        currency: str,
        due_date: datetime,
        status: str,
        pdf_attachment: Optional[dict] = None
    ) -> bool:
        """
        Send invoice notification email.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email address
            to_name: Recipient name
            invoice_number: Invoice number (e.g., INV-20251118-0001)
            total_amount: Invoice total amount
            currency: Currency code (NGN, USD, etc.)
            due_date: Invoice due date
            status: Invoice status (pending, completed, etc.)
            pdf_attachment: Optional PDF attachment dict with filename, content, content_type

        Returns:
            True if email was published successfully, False otherwise
        """
        # Format amount based on currency
        if currency == "NGN":
            formatted_amount = f"₦{total_amount:,.2f}"
        elif currency == "USD":
            formatted_amount = f"${total_amount:,.2f}"
        else:
            formatted_amount = f"{currency} {total_amount:,.2f}"

        # Format due date
        formatted_due_date = due_date.strftime("%B %d, %Y") if due_date else "N/A"

        # Determine subject and message based on status
        if status == "completed":
            subject = f"Invoice {invoice_number} - Payment Received"
            status_text = "Your payment has been received! Thank you for your business."
            status_color = "#4CAF50"
        else:
            subject = f"Invoice {invoice_number} - Ready for Payment"
            status_text = f"Your invoice is ready. Please complete payment by {formatted_due_date}."
            status_color = "#FF9800"

        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #2B55FF 0%, #1E3FCC 100%); padding: 30px; text-align: center; position: relative;">
                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                    <h1 style="color: #ffffff; margin: 0; font-size: 28px;">ChatCraft</h1>
                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Invoice Notification</p>
                </div>

                <!-- Body -->
                <div style="padding: 30px;">
                    <p style="font-size: 16px; color: #333; margin-bottom: 20px;">Hello {to_name},</p>

                    <!-- Status Badge -->
                    <div style="background-color: {status_color}; color: white; padding: 10px 20px; border-radius: 5px; display: inline-block; margin-bottom: 20px;">
                        <strong>{status_text}</strong>
                    </div>

                    <!-- Invoice Details Box -->
                    <div style="background-color: #f9f9f9; border-left: 4px solid #2B55FF; padding: 20px; margin: 20px 0;">
                        <h2 style="margin: 0 0 15px 0; color: #2B55FF; font-size: 20px;">Invoice Details</h2>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Invoice Number:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{invoice_number}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Amount:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;"><strong style="font-size: 18px; color: #2B55FF;">{formatted_amount}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Status:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{status.title()}</td>
                            </tr>
                            {f'<tr><td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Due Date:</strong></td><td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{formatted_due_date}</td></tr>' if status != 'completed' else ''}
                        </table>
                    </div>

                    <!-- PDF Attachment Notice -->
                    <div style="background-color: #E3F2FD; border-left: 4px solid #2196F3; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0; color: #1565C0; font-size: 14px;">
                            📎 <strong>Invoice PDF Attached</strong><br>
                            Your invoice is attached to this email as a PDF document. You can download and save it for your records.
                        </p>
                    </div>

                    <!-- Additional Information -->
                    {'''
                    <div style="background-color: #FFF3CD; border-left: 4px solid #FFC107; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0; color: #856404; font-size: 14px;">
                            <strong>⚠️ Payment Required</strong><br>
                            Please ensure payment is completed by ''' + formatted_due_date + ''' to avoid service interruption.
                        </p>
                    </div>
                    ''' if status != 'completed' else ''}

                    <p style="font-size: 14px; color: #666; margin-top: 30px;">
                        The invoice PDF is attached to this email for your records.
                    </p>

                    <p style="font-size: 14px; color: #666; margin-top: 20px;">
                        If you have any questions about this invoice, please don't hesitate to contact our support team.
                    </p>

                    <p style="font-size: 14px; color: #333; margin-top: 30px;">
                        Best regards,<br>
                        <strong>The ChatCraft Team</strong>
                    </p>
                </div>

                <!-- Footer -->
                <div style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                    <div style="height: 2px; width: 60px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 1px;"></div>
                    <p style="font-size: 12px; color: #888; margin: 0;">
                        This is an automated email. Please do not reply to this message.
                    </p>
                    <p style="font-size: 12px; color: #888; margin: 10px 0 0 0;">
                        Need help? Contact us at <a href="mailto:support@chatcraft.cc" style="color: #2B55FF; text-decoration: none;">support@chatcraft.cc</a>
                    </p>
                    <p style="font-size: 12px; color: #888; margin: 5px 0 0 0;">
                        Visit us at <a href="https://www.chatcraft.cc" style="color: #2B55FF; text-decoration: none;">www.chatcraft.cc</a>
                    </p>
                    <p style="font-size: 12px; color: #888; margin: 10px 0 0 0;">
                        © {datetime.now().year} ChatCraft. All rights reserved.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""Hello {to_name},

{status_text}

Invoice Details:
- Invoice Number: {invoice_number}
- Amount: {formatted_amount}
- Status: {status.title()}
{f'- Due Date: {formatted_due_date}' if status != 'completed' else ''}

📎 INVOICE PDF ATTACHED
Your invoice is attached to this email as a PDF document. You can download and save it for your records.

The invoice PDF is attached to this email for your records.

If you have any questions about this invoice, please contact our support team.

Best regards,
The ChatCraft Team
"""

        # Prepare attachments list
        attachments = [pdf_attachment] if pdf_attachment else None

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            attachments=attachments
        )

    async def publish_usage_warning_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        plan_name: str,
        usage_type: str,
        current_usage: int,
        limit: int,
        percentage: int,
        threshold_level: str,
        severity: str
    ) -> bool:
        """
        Send usage warning email when approaching limits.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            plan_name: Current plan name
            usage_type: Type of usage (e.g., "document uploads", "monthly chat messages")
            current_usage: Current usage count
            limit: Maximum allowed
            percentage: Usage percentage (0-100)
            threshold_level: "80", "90", or "100"
            severity: "medium", "high", or "critical"

        Returns:
            True if email published successfully
        """
        # Severity colors
        severity_colors = {
            "medium": "#FF9800",   # Orange
            "high": "#FF5722",     # Deep orange
            "critical": "#F44336"  # Red
        }
        severity_color = severity_colors.get(severity, "#FF9800")

        # Determine subject and message
        if threshold_level == "100":
            subject = f"🚨 ChatCraft {plan_name} - Limit Reached!"
            status_text = "You've reached your limit"
            emoji = "🚨"
            urgency = "URGENT"
        elif threshold_level == "90":
            subject = f"⚠️ ChatCraft {plan_name} - 90% Limit Reached"
            status_text = "You're approaching your limit"
            emoji = "⚠️"
            urgency = "IMPORTANT"
        else:
            subject = f"📊 ChatCraft {plan_name} - 80% Limit Reached"
            status_text = "You're using most of your quota"
            emoji = "📊"
            urgency = "NOTICE"

        remaining = max(0, limit - current_usage)

        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #5D3EC1 0%, #7B5FD9 100%); padding: 30px; text-align: center; position: relative;">
                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                    <h1 style="color: #ffffff; margin: 0; font-size: 28px;">ChatCraft</h1>
                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">{plan_name} Plan</p>
                </div>

                <!-- Alert Banner -->
                <div style="background-color: {severity_color}; color: white; padding: 20px; text-align: center;">
                    <div style="font-size: 48px; margin-bottom: 10px;">{emoji}</div>
                    <h2 style="margin: 0; font-size: 24px;">{urgency}: {status_text}</h2>
                </div>

                <!-- Body -->
                <div style="padding: 30px;">
                    <p style="font-size: 16px; color: #333; margin-bottom: 20px;">Hello {to_name},</p>

                    <p style="font-size: 16px; color: #333; margin-bottom: 30px;">
                        You've used <strong>{percentage}%</strong> of your {usage_type} quota for this billing period.
                    </p>

                    <!-- Usage Stats Box -->
                    <div style="background-color: #f9f9f9; border-left: 4px solid {severity_color}; padding: 20px; margin: 20px 0;">
                        <h3 style="margin: 0 0 15px 0; color: {severity_color}; font-size: 18px;">Usage Details</h3>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Resource:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{usage_type.title()}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Current Usage:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{current_usage:,} / {limit:,}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Percentage:</strong></td>
                                <td style="padding: 8px 0; font-size: 14px; text-align: right;">
                                    <strong style="font-size: 18px; color: {severity_color};">{percentage}%</strong>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Remaining:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{remaining:,}</td>
                            </tr>
                        </table>
                    </div>

                    <!-- Progress Bar -->
                    <div style="margin: 30px 0;">
                        <div style="background-color: #e0e0e0; height: 30px; border-radius: 15px; overflow: hidden; position: relative;">
                            <div style="background: linear-gradient(90deg, {severity_color} 0%, {severity_color} 100%); height: 100%; width: {percentage}%; transition: width 0.3s ease;"></div>
                            <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: #333; font-weight: bold; font-size: 14px;">
                                {percentage}% Used
                            </div>
                        </div>
                    </div>

                    {"" if threshold_level != "100" else f'''
                    <!-- Limit Reached Warning -->
                    <div style="background-color: #FFEBEE; border-left: 4px solid #F44336; padding: 15px; margin: 20px 0;">
                        <p style="margin: 0; color: #C62828; font-size: 14px;">
                            <strong>⛔ Limit Reached</strong><br>
                            You cannot perform additional {usage_type} until you upgrade your plan or your usage resets.
                        </p>
                    </div>
                    '''}

                    <!-- Upgrade CTA -->
                    <div style="background-color: #E3F2FD; border-left: 4px solid #2196F3; padding: 20px; margin: 30px 0;">
                        <h3 style="margin: 0 0 10px 0; color: #1976D2; font-size: 18px;">Need More Capacity?</h3>
                        <p style="margin: 0 0 15px 0; color: #1565C0; font-size: 14px;">
                            Upgrade your plan to get more {usage_type} and unlock additional features!
                        </p>
                        <div style="text-align: center; margin-top: 20px;">
                            <a href="https://chatcraft.com/billing/upgrade" style="display: inline-block; background-color: #2196F3; color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">Upgrade Now</a>
                        </div>
                    </div>

                    <p style="font-size: 14px; color: #666; margin-top: 30px;">
                        {"Your usage will reset at the start of your next billing period." if threshold_level != "100" else "To continue using this feature immediately, please upgrade your plan."}
                    </p>

                    <p style="font-size: 14px; color: #333; margin-top: 30px;">
                        Best regards,<br>
                        <strong>The ChatCraft Team</strong>
                    </p>
                </div>

                <!-- Footer -->
                <div style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #888; margin: 0;">
                        This is an automated notification. Please do not reply to this message.
                    </p>
                    <p style="font-size: 12px; color: #888; margin: 10px 0 0 0;">
                        © {datetime.now().year} ChatCraft. All rights reserved.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        text_content = f"""Hello {to_name},

{urgency}: {status_text}

You've used {percentage}% of your {usage_type} quota for this billing period.

Usage Details:
- Resource: {usage_type.title()}
- Current Usage: {current_usage:,} / {limit:,}
- Percentage: {percentage}%
- Remaining: {remaining:,}

{"⛔ LIMIT REACHED: You cannot perform additional " + usage_type + " until you upgrade your plan or your usage resets." if threshold_level == "100" else ""}

Need More Capacity?
Upgrade your plan to get more {usage_type} and unlock additional features!

Upgrade now: https://chatcraft.com/billing/upgrade

{"Your usage will reset at the start of your next billing period." if threshold_level != "100" else "To continue using this feature immediately, please upgrade your plan."}

Best regards,
The ChatCraft Team
"""

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    async def publish_payment_receipt_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        amount: float,
        currency: str,
        payment_reference: str,
        payment_date: datetime,
        plan_name: str
    ) -> bool:
        """
        Send payment receipt email after successful payment.

        Args:
            tenant_id: Tenant ID
            to_email: Recipient email
            to_name: Recipient name
            amount: Payment amount
            currency: Currency code
            payment_reference: Payment reference number
            payment_date: Date of payment
            plan_name: Plan name

        Returns:
            True if email published successfully
        """
        # Get logo data URL for email embedding
        logo_data_url = get_logo_data_url("chatcraft-logo-white.png")

        # Format amount
        if currency == "NGN":
            formatted_amount = f"₦{amount:,.2f}"
        elif currency == "USD":
            formatted_amount = f"${amount:,.2f}"
        else:
            formatted_amount = f"{currency} {amount:,.2f}"

        # Format date
        formatted_date = payment_date.strftime("%B %d, %Y at %I:%M %p UTC")

        subject = f"Payment Receipt - {formatted_amount} - ChatCraft"

        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background-color: #f5f5f5;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="margin: 0 auto; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); overflow: hidden;">
                            <!-- Header with Logo and Branding -->
                            <tr>
                                <td style="background: linear-gradient(135deg, #4CAF50 0%, #388E3C 100%); padding: 30px; text-align: center; position: relative;">
                                    {f'<img src="{logo_data_url}" alt="ChatCraft" style="max-width: 150px; height: auto; margin-bottom: 15px;">' if logo_data_url else ''}
                                    <div style="height: 3px; width: 80px; background-color: #CDF547; margin: 0 auto 15px auto; border-radius: 2px;"></div>
                                    <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: 600;">ChatCraft</h1>
                                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Payment Receipt</p>
                                </td>
                            </tr>

                            <!-- Main Content -->
                            <tr>
                                <td style="padding: 40px 30px;">
                                    <h2 style="color: #333333; font-size: 24px; margin: 0 0 20px 0; font-weight: 600;">Hello {to_name},</h2>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 0 0 20px 0;">
                                        We've successfully received your payment. Thank you for your business!
                                    </p>

                                    <!-- Success Box -->
                                    <div style="background-color: #E8F5E9; border-left: 4px solid #4CAF50; padding: 15px; margin: 20px 0; border-radius: 4px;">
                                        <p style="color: #2E7D32; font-size: 14px; line-height: 1.6; margin: 0;">
                                            <strong>Payment Confirmed:</strong> Your payment has been processed successfully.
                                        </p>
                                    </div>

                                    <!-- Payment Details Box -->
                                    <div style="background-color: #f9f9f9; border-left: 4px solid #4CAF50; padding: 20px; margin: 20px 0; border-radius: 4px;">
                                        <h3 style="margin: 0 0 15px 0; color: #4CAF50; font-size: 18px; font-weight: 600;">Payment Details</h3>
                                        <table style="width: 100%; border-collapse: collapse;">
                                            <tr>
                                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Amount Paid:</strong></td>
                                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;"><strong style="font-size: 18px; color: #4CAF50;">{formatted_amount}</strong></td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Plan:</strong></td>
                                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{plan_name}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Payment Date:</strong></td>
                                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{formatted_date}</td>
                                            </tr>
                                            <tr>
                                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Reference:</strong></td>
                                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right; font-family: monospace;">{payment_reference}</td>
                                            </tr>
                                        </table>
                                    </div>

                                    <p style="color: #555555; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                                        Your invoice has been generated and is available in your account dashboard. You can view and download it anytime.
                                    </p>

                                    <!-- CTA Button -->
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="https://app.chatcraft.cc/invoices" style="background-color: #4CAF50; color: #ffffff; text-decoration: none; padding: 14px 32px; border-radius: 6px; font-size: 16px; font-weight: 600; display: inline-block;">
                                            View Invoice
                                        </a>
                                    </div>

                                    <p style="color: #555555; font-size: 14px; line-height: 1.6; margin: 20px 0 0 0;">
                                        If you have any questions about this payment, please don't hesitate to contact our support team.
                                    </p>

                                    <p style="color: #555555; font-size: 14px; line-height: 1.6; margin: 20px 0 0 0; font-style: italic;">
                                        Keep this email for your records.
                                    </p>
                                </td>
                            </tr>

                            <!-- Footer -->
                            <tr>
                                <td style="background-color: #f9f9f9; padding: 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                                    <p style="color: #666666; font-size: 14px; margin: 0 0 10px 0;">
                                        Thank you for choosing ChatCraft!<br>
                                        <strong>The ChatCraft Team</strong>
                                    </p>
                                    <p style="color: #999999; font-size: 12px; margin: 15px 0 0 0;">
                                        <a href="https://chatcraft.cc" style="color: #4CAF50; text-decoration: none;">ChatCraft</a> |
                                        <a href="https://chatcraft.cc/support" style="color: #4CAF50; text-decoration: none;">Support</a> |
                                        <a href="https://chatcraft.cc/privacy" style="color: #4CAF50; text-decoration: none;">Privacy Policy</a>
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        text_content = f"""Hello {to_name},

✅ Payment Successful!

We've successfully received your payment. Here are the details:

Payment Details:
- Amount Paid: {formatted_amount}
- Plan: {plan_name}
- Payment Date: {formatted_date}
- Reference: {payment_reference}

Your invoice has been generated and is available in your account dashboard.

View your invoice: https://chatcraft.com/invoices

If you have any questions about this payment, please contact our support team.

Thank you for choosing ChatCraft!

Best regards,
The ChatCraft Team
"""

        return await self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

# Global instance
email_publisher = EmailPublisher()

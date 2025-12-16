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
from datetime import datetime, timezone
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
                "queued_at": datetime.now(timezone.utc).isoformat()
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

    def publish_plan_upgraded_email(
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
        # Format amount
        if currency == "NGN":
            formatted_amount = f"₦{proration_amount:,.2f}"
        elif currency == "USD":
            formatted_amount = f"${proration_amount:,.2f}"
        else:
            formatted_amount = f"{proration_amount:,.2f} {currency}"

        subject = f"Your ChatCraft Plan Has Been Upgraded to {new_plan_name}"
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Hello {to_name},</h2>
            <p>Great news! Your ChatCraft subscription has been upgraded from <strong>{old_plan_name}</strong> to <strong>{new_plan_name}</strong>.</p>
            <p>You now have access to all the enhanced features and limits of the {new_plan_name} plan.</p>
            <p>A prorated charge of <strong>{formatted_amount}</strong> has been applied for the remaining days in your current billing period.</p>
            <p>Thank you for choosing ChatCraft!</p>
            <p>Best regards,<br>The ChatCraft Team</p>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nGreat news! Your ChatCraft subscription has been upgraded from {old_plan_name} to {new_plan_name}.\n\nYou now have access to all the enhanced features and limits of the {new_plan_name} plan.\n\nA prorated charge of {formatted_amount} has been applied for the remaining days in your current billing period.\n\nThank you for choosing ChatCraft!\n\nBest regards,\nThe ChatCraft Team"

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_plan_downgraded_email(
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

        formatted_date = effective_date.strftime("%B %d, %Y")

        if immediate:
            subject = f"Your ChatCraft Plan Has Been Changed to {new_plan_name}"
            timing_text = "Your plan has been changed immediately."
        else:
            subject = f"Your ChatCraft Plan Will Change to {new_plan_name} on {formatted_date}"
            timing_text = f"Your plan will change to {new_plan_name} on <strong>{formatted_date}</strong>."

        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Hello {to_name},</h2>
            <p>Your ChatCraft subscription plan is changing from <strong>{old_plan_name}</strong> to <strong>{new_plan_name}</strong>.</p>
            <p>{timing_text}</p>
            {'' if immediate else f'<p>You will continue to have access to all {old_plan_name} features until {formatted_date}.</p>'}
            <p>If you have any questions or would like to keep your current plan, please contact our support team.</p>
            <p>Best regards,<br>The ChatCraft Team</p>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nYour ChatCraft subscription plan is changing from {old_plan_name} to {new_plan_name}.\n\n{timing_text.replace('<strong>', '').replace('</strong>', '')}\n\n{'' if immediate else f'You will continue to have access to all {old_plan_name} features until {formatted_date}.'}If you have any questions or would like to keep your current plan, please contact our support team.\n\nBest regards,\nThe ChatCraft Team"

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_subscription_cancelled_email(
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
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h2>Hello {to_name},</h2>
            <p>We're sorry to see you go!</p>
            <p>Your ChatCraft <strong>{plan_name}</strong> subscription is being cancelled.</p>
            <p>{timing_text}</p>
            {access_text}
            <p>If you change your mind or cancelled by mistake, you can reactivate your subscription anytime from your account settings.</p>
            <p>We'd love to hear your feedback on how we can improve. Please feel free to reach out to our support team.</p>
            <p>Best regards,<br>The ChatCraft Team</p>
        </body>
        </html>
        """
        text_content = f"Hello {to_name},\n\nWe're sorry to see you go!\n\nYour ChatCraft {plan_name} subscription is being cancelled.\n\n{timing_text.replace('<strong>', '').replace('</strong>', '')}\n\n{access_text.replace('<p>', '').replace('</p>', '')}If you change your mind or cancelled by mistake, you can reactivate your subscription anytime from your account settings.\n\nWe'd love to hear your feedback on how we can improve. Please feel free to reach out to our support team.\n\nBest regards,\nThe ChatCraft Team"

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_invoice_email(
        self,
        tenant_id: str,
        to_email: str,
        to_name: str,
        invoice_number: str,
        total_amount: float,
        currency: str,
        due_date: datetime,
        status: str
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
                <div style="background: linear-gradient(135deg, #5D3EC1 0%, #7B5FD9 100%); padding: 30px; text-align: center;">
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
                    <div style="background-color: #f9f9f9; border-left: 4px solid #5D3EC1; padding: 20px; margin: 20px 0;">
                        <h2 style="margin: 0 0 15px 0; color: #5D3EC1; font-size: 20px;">Invoice Details</h2>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Invoice Number:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{invoice_number}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Amount:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;"><strong style="font-size: 18px; color: #5D3EC1;">{formatted_amount}</strong></td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Status:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{status.title()}</td>
                            </tr>
                            {f'<tr><td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Due Date:</strong></td><td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;">{formatted_due_date}</td></tr>' if status != 'completed' else ''}
                        </table>
                    </div>

                    <!-- Action Button -->
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://chatcraft.com/invoices/{invoice_number}" style="display: inline-block; background-color: #5D3EC1; color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">View Invoice</a>
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
                        You can view and download your invoice anytime from your ChatCraft dashboard.
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
                    <p style="font-size: 12px; color: #888; margin: 0;">
                        This is an automated email. Please do not reply to this message.
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

View your invoice online: https://chatcraft.com/invoices/{invoice_number}

You can view and download your invoice anytime from your ChatCraft dashboard.

If you have any questions about this invoice, please contact our support team.

Best regards,
The ChatCraft Team
"""

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_usage_warning_email(
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
                <div style="background: linear-gradient(135deg, #5D3EC1 0%, #7B5FD9 100%); padding: 30px; text-align: center;">
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

        return self.publish_email(
            tenant_id=tenant_id,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_content=html_content,
            text_content=text_content
        )

    def publish_payment_receipt_email(
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
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>{subject}</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f4f4f4;">
            <div style="max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <!-- Header -->
                <div style="background: linear-gradient(135deg, #4CAF50 0%, #66BB6A 100%); padding: 30px; text-align: center;">
                    <div style="font-size: 64px; margin-bottom: 10px;">✅</div>
                    <h1 style="color: #ffffff; margin: 0; font-size: 28px;">Payment Successful!</h1>
                    <p style="color: #ffffff; margin: 10px 0 0 0; font-size: 16px; opacity: 0.9;">Thank you for your payment</p>
                </div>

                <!-- Body -->
                <div style="padding: 30px;">
                    <p style="font-size: 16px; color: #333; margin-bottom: 20px;">Hello {to_name},</p>

                    <p style="font-size: 16px; color: #333; margin-bottom: 30px;">
                        We've successfully received your payment. Here are the details:
                    </p>

                    <!-- Payment Details Box -->
                    <div style="background-color: #f9f9f9; border-left: 4px solid #4CAF50; padding: 20px; margin: 20px 0;">
                        <h2 style="margin: 0 0 15px 0; color: #4CAF50; font-size: 20px;">Payment Details</h2>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr>
                                <td style="padding: 8px 0; color: #666; font-size: 14px;"><strong>Amount Paid:</strong></td>
                                <td style="padding: 8px 0; color: #333; font-size: 14px; text-align: right;"><strong style="font-size: 20px; color: #4CAF50;">{formatted_amount}</strong></td>
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

                    <!-- View Invoice Button -->
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="https://chatcraft.com/invoices" style="display: inline-block; background-color: #5D3EC1; color: #ffffff; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; font-size: 16px;">View Invoice</a>
                    </div>

                    <p style="font-size: 14px; color: #666; margin-top: 30px;">
                        Your invoice has been generated and is available in your account dashboard. You can view and download it anytime.
                    </p>

                    <p style="font-size: 14px; color: #666; margin-top: 20px;">
                        If you have any questions about this payment, please don't hesitate to contact our support team.
                    </p>

                    <p style="font-size: 14px; color: #333; margin-top: 30px;">
                        Thank you for choosing ChatCraft!<br>
                        <strong>The ChatCraft Team</strong>
                    </p>
                </div>

                <!-- Footer -->
                <div style="background-color: #f9f9f9; padding: 20px; text-align: center; border-top: 1px solid #eee;">
                    <p style="font-size: 12px; color: #888; margin: 0;">
                        Keep this email for your records.
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

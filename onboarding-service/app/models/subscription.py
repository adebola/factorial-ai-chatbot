import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import Column, String, DateTime, Boolean, Text, JSON, Enum, ForeignKey, Numeric, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import enum

Base = declarative_base()


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    PENDING = "pending"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIALING = "trialing"


class BillingCycle(str, enum.Enum):
    MONTHLY = "monthly"
    YEARLY = "yearly"


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentMethod(str, enum.Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    USSD = "ussd"
    QR = "qr"
    MOBILE_MONEY = "mobile_money"


class TransactionType(str, enum.Enum):
    SUBSCRIPTION = "subscription"
    UPGRADE = "upgrade"
    DOWNGRADE = "downgrade"
    RENEWAL = "renewal"
    REFUND = "refund"


class Subscription(Base):
    """Core subscription model for tenant plan subscriptions"""
    __tablename__ = "subscriptions"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)  # Tenant data in OAuth2 server
    plan_id = Column(String(36), ForeignKey("plans.id"), nullable=False, index=True)
    
    # Subscription details
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING, nullable=False)
    billing_cycle = Column(Enum(BillingCycle), default=BillingCycle.MONTHLY, nullable=False)
    
    # Pricing and billing
    amount = Column(Numeric(10, 2), nullable=False)  # Current subscription amount
    currency = Column(String(3), default="NGN", nullable=False)  # NGN, USD, etc.
    
    # Subscription lifecycle dates
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=False)
    current_period_start = Column(DateTime(timezone=True), nullable=False)
    current_period_end = Column(DateTime(timezone=True), nullable=False)
    
    # Trial period
    trial_starts_at = Column(DateTime(timezone=True), nullable=True)
    trial_ends_at = Column(DateTime(timezone=True), nullable=True)
    
    # Cancellation
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)
    
    # Grace period for failed payments
    grace_period_ends_at = Column(DateTime(timezone=True), nullable=True)
    
    # Auto-renewal
    auto_renew = Column(Boolean, default=True, nullable=False)
    
    # Metadata
    subscription_metadata = Column(JSON, default={})  # Additional subscription data
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    payments = relationship("Payment", back_populates="subscription")
    subscription_changes = relationship("SubscriptionChange", back_populates="subscription")
    invoices = relationship("Invoice", back_populates="subscription")


class Payment(Base):
    """Payment transaction records"""
    __tablename__ = "payments"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)  # Tenant data in OAuth2 server
    
    # Payment details
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="NGN", nullable=False)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    payment_method = Column(Enum(PaymentMethod), nullable=True)
    transaction_type = Column(Enum(TransactionType), default=TransactionType.SUBSCRIPTION, nullable=False)
    
    # Paystack integration
    paystack_reference = Column(String(255), unique=True, nullable=True, index=True)
    paystack_access_code = Column(String(255), nullable=True)
    paystack_transaction_id = Column(String(255), nullable=True, index=True)
    
    # Payment processing
    gateway_response = Column(JSON, default={})  # Paystack response data
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Description and metadata
    description = Column(Text, nullable=True)
    payment_metadata = Column(JSON, default={})
    
    # Refund information
    refunded_amount = Column(Numeric(10, 2), default=0.00, nullable=False)
    refund_reason = Column(Text, nullable=True)
    refunded_at = Column(DateTime(timezone=True), nullable=True)
    
    # Failure information
    failure_reason = Column(Text, nullable=True)
    failure_code = Column(String(50), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    subscription = relationship("Subscription", back_populates="payments")


class PaymentMethodRecord(Base):
    """Store customer payment methods"""
    __tablename__ = "payment_methods"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)  # Tenant data in OAuth2 server
    
    # Payment method details
    type = Column(Enum(PaymentMethod), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    
    # Card information (masked)
    card_last_four = Column(String(4), nullable=True)
    card_brand = Column(String(20), nullable=True)  # visa, mastercard, etc.
    card_exp_month = Column(Integer, nullable=True)
    card_exp_year = Column(Integer, nullable=True)
    
    # Bank information
    bank_name = Column(String(100), nullable=True)
    account_name = Column(String(255), nullable=True)
    
    # Paystack authorization
    paystack_authorization_code = Column(String(255), nullable=True, index=True)
    paystack_customer_code = Column(String(255), nullable=True, index=True)
    
    # Metadata
    payment_method_metadata = Column(JSON, default={})
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Invoice(Base):
    """Generated invoices for billing periods"""
    __tablename__ = "invoices"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)  # Tenant data in OAuth2 server
    
    # Invoice details
    invoice_number = Column(String(50), unique=True, nullable=False, index=True)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    
    # Amounts
    subtotal = Column(Numeric(10, 2), nullable=False)
    tax_amount = Column(Numeric(10, 2), default=0.00, nullable=False)
    total_amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="NGN", nullable=False)
    
    # Billing period
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    
    # Due date
    due_date = Column(DateTime(timezone=True), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    
    # Invoice data
    line_items = Column(JSON, default=[])  # Detailed billing items
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    subscription = relationship("Subscription", back_populates="invoices")


class SubscriptionChange(Base):
    """Audit trail for subscription modifications"""
    __tablename__ = "subscription_changes"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)  # Tenant data in OAuth2 server
    
    # Change details
    change_type = Column(String(50), nullable=False)  # upgrade, downgrade, cancel, renew
    previous_plan_id = Column(String(36), nullable=True)
    new_plan_id = Column(String(36), nullable=True)
    
    # Financial impact
    previous_amount = Column(Numeric(10, 2), nullable=True)
    new_amount = Column(Numeric(10, 2), nullable=True)
    prorated_amount = Column(Numeric(10, 2), nullable=True)
    
    # Change metadata
    reason = Column(Text, nullable=True)
    initiated_by = Column(String(50), nullable=True)  # user, system, admin
    change_metadata = Column(JSON, default={})
    
    # Effective dates
    effective_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    subscription = relationship("Subscription", back_populates="subscription_changes")


class PaystackWebhook(Base):
    """Log Paystack webhook events"""
    __tablename__ = "paystack_webhooks"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    
    # Webhook details
    event_type = Column(String(100), nullable=False, index=True)
    paystack_event_id = Column(String(255), unique=True, nullable=False, index=True)
    
    # Processing status
    processed = Column(Boolean, default=False, nullable=False)
    processing_attempts = Column(Integer, default=0, nullable=False)
    last_processing_error = Column(Text, nullable=True)
    
    # Event data
    raw_data = Column(JSON, nullable=False)  # Complete webhook payload
    signature = Column(String(255), nullable=False)  # Webhook signature for verification
    
    # Related records
    payment_id = Column(String(36), nullable=True, index=True)
    subscription_id = Column(String(36), nullable=True, index=True)
    
    # Timestamps
    received_at = Column(DateTime(timezone=True), server_default=func.now())
    processed_at = Column(DateTime(timezone=True), nullable=True)


class UsageTracking(Base):
    """Track API usage against subscription limits"""
    __tablename__ = "usage_tracking"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(36), nullable=False, index=True)  # Tenant data in OAuth2 server
    subscription_id = Column(String(36), ForeignKey("subscriptions.id"), nullable=False, index=True)
    
    # Usage metrics
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    
    # Current usage
    documents_used = Column(Integer, default=0, nullable=False)
    websites_used = Column(Integer, default=0, nullable=False)
    daily_chats_used = Column(Integer, default=0, nullable=False)
    monthly_chats_used = Column(Integer, default=0, nullable=False)
    
    # API calls
    api_calls_made = Column(Integer, default=0, nullable=False)
    
    # Last reset dates
    daily_reset_at = Column(DateTime(timezone=True), nullable=True)
    monthly_reset_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class RefundRequest(Base):
    """Handle refund requests and processing"""
    __tablename__ = "refund_requests"
    
    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    payment_id = Column(String(36), ForeignKey("payments.id"), nullable=False, index=True)
    tenant_id = Column(String(36), nullable=False, index=True)  # Tenant data in OAuth2 server
    
    # Refund details
    requested_amount = Column(Numeric(10, 2), nullable=False)
    approved_amount = Column(Numeric(10, 2), nullable=True)
    currency = Column(String(3), default="NGN", nullable=False)
    
    # Status and processing
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING, nullable=False)
    reason = Column(Text, nullable=False)
    admin_notes = Column(Text, nullable=True)
    
    # Paystack refund reference
    paystack_refund_id = Column(String(255), nullable=True, index=True)
    gateway_response = Column(JSON, default={})
    
    # Approval workflow
    requested_by = Column(String(36), nullable=False)  # User ID who requested
    approved_by = Column(String(36), nullable=True)    # Admin who approved
    approved_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
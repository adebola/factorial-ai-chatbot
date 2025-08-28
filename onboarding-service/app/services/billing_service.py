from decimal import Decimal
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
import uuid

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from ..core.config import settings
from ..models.tenant import Tenant
from ..models.subscription import (
    Subscription, SubscriptionStatus, BillingCycle, Payment, PaymentStatus,
    TransactionType, Invoice, UsageTracking, PaymentMethodRecord
)
from .paystack_service import PaystackService
from .subscription_service import SubscriptionService


class BillingService:
    """Service for automated billing and subscription lifecycle management"""
    
    def __init__(self, db: Session):
        self.db = db
        self.paystack = PaystackService(db)
        self.subscription_service = SubscriptionService(db)
    
    async def process_renewals(self) -> Dict[str, Any]:
        """Process subscription renewals for subscriptions ending today"""
        
        today = datetime.utcnow().date()
        
        # Find subscriptions that need renewal
        expiring_subscriptions = self.db.query(Subscription).filter(
            and_(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
                Subscription.current_period_end <= datetime.combine(today, datetime.min.time()) + timedelta(days=1),
                Subscription.auto_renew == True,
                Subscription.cancel_at_period_end == False
            )
        ).all()
        
        renewal_results = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "results": []
        }
        
        for subscription in expiring_subscriptions:
            result = await self._process_subscription_renewal(subscription)
            renewal_results["results"].append(result)
            renewal_results["processed"] += 1
            
            if result["success"]:
                renewal_results["successful"] += 1
            else:
                renewal_results["failed"] += 1
        
        return renewal_results
    
    async def _process_subscription_renewal(self, subscription: Subscription) -> Dict[str, Any]:
        """Process renewal for a single subscription"""
        
        try:
            # Get tenant information
            tenant = self.db.query(Tenant).filter(Tenant.id == subscription.tenant_id).first()
            if not tenant:
                return {
                    "subscription_id": subscription.id,
                    "success": False,
                    "error": "Tenant not found"
                }
            
            # Check if trial period is ending
            if subscription.status == SubscriptionStatus.TRIALING:
                # End trial and activate subscription
                return await self._end_trial_period(subscription, tenant)
            
            # For active subscriptions, attempt automatic billing
            return await self._attempt_automatic_billing(subscription, tenant)
            
        except Exception as e:
            return {
                "subscription_id": subscription.id,
                "success": False,
                "error": str(e)
            }
    
    async def _end_trial_period(self, subscription: Subscription, tenant: Tenant) -> Dict[str, Any]:
        """End trial period and attempt first payment"""
        
        # Check if tenant has a saved payment method
        payment_method = self.db.query(PaymentMethodRecord).filter(
            and_(
                PaymentMethodRecord.tenant_id == tenant.id,
                PaymentMethodRecord.is_default == True,
                PaymentMethodRecord.is_active == True
            )
        ).first()
        
        if not payment_method or not payment_method.paystack_authorization_code:
            # No payment method available, move to past due
            subscription.status = SubscriptionStatus.PAST_DUE
            subscription.grace_period_ends_at = datetime.utcnow() + timedelta(
                days=settings.SUBSCRIPTION_GRACE_PERIOD_DAYS
            )
            self.db.commit()
            
            return {
                "subscription_id": subscription.id,
                "success": False,
                "error": "No payment method available",
                "action": "moved_to_past_due"
            }
        
        # Attempt to charge the saved payment method
        return await self._charge_payment_method(subscription, tenant, payment_method, TransactionType.RENEWAL)
    
    async def _attempt_automatic_billing(self, subscription: Subscription, tenant: Tenant) -> Dict[str, Any]:
        """Attempt automatic billing for subscription renewal"""
        
        # Get default payment method
        payment_method = self.db.query(PaymentMethodRecord).filter(
            and_(
                PaymentMethodRecord.tenant_id == tenant.id,
                PaymentMethodRecord.is_default == True,
                PaymentMethodRecord.is_active == True
            )
        ).first()
        
        if not payment_method or not payment_method.paystack_authorization_code:
            # No payment method, move to past due
            subscription.status = SubscriptionStatus.PAST_DUE
            subscription.grace_period_ends_at = datetime.utcnow() + timedelta(
                days=settings.SUBSCRIPTION_GRACE_PERIOD_DAYS
            )
            self.db.commit()
            
            return {
                "subscription_id": subscription.id,
                "success": False,
                "error": "No payment method available",
                "action": "moved_to_past_due"
            }
        
        # Attempt to charge
        return await self._charge_payment_method(subscription, tenant, payment_method, TransactionType.RENEWAL)
    
    async def _charge_payment_method(
        self,
        subscription: Subscription,
        tenant: Tenant,
        payment_method: PaymentMethodRecord,
        transaction_type: TransactionType
    ) -> Dict[str, Any]:
        """Charge a saved payment method"""
        
        # Generate payment reference
        reference = f"renewal_{subscription.id}_{uuid.uuid4().hex[:8]}"
        
        # Prepare metadata
        metadata = {
            "subscription_id": subscription.id,
            "tenant_id": tenant.id,
            "plan_id": subscription.plan_id,
            "billing_cycle": subscription.billing_cycle.value,
            "transaction_type": transaction_type.value,
            "auto_renewal": True
        }
        
        # Attempt charge
        charge_result = await self.paystack.charge_authorization(
            authorization_code=payment_method.paystack_authorization_code,
            email=tenant.email,
            amount=subscription.amount,
            currency=subscription.currency,
            reference=reference,
            metadata=metadata
        )
        
        if charge_result["success"]:
            # Create payment record
            payment = Payment(
                subscription_id=subscription.id,
                tenant_id=tenant.id,
                amount=subscription.amount,
                currency=subscription.currency,
                status=PaymentStatus.COMPLETED,
                transaction_type=transaction_type,
                paystack_reference=reference,
                description=f"Automatic renewal for {subscription.billing_cycle.value} subscription",
                metadata=metadata,
                processed_at=datetime.utcnow(),
                gateway_response=charge_result["data"]
            )
            
            self.db.add(payment)
            
            # Update subscription for next period
            self._update_subscription_for_next_period(subscription)
            
            # Reset usage tracking
            self._reset_usage_tracking(subscription)
            
            self.db.commit()
            
            return {
                "subscription_id": subscription.id,
                "success": True,
                "payment_id": payment.id,
                "amount": float(subscription.amount),
                "reference": reference
            }
        else:
            # Payment failed, move to past due
            subscription.status = SubscriptionStatus.PAST_DUE
            subscription.grace_period_ends_at = datetime.utcnow() + timedelta(
                days=settings.SUBSCRIPTION_GRACE_PERIOD_DAYS
            )
            
            # Record failed payment
            payment = Payment(
                subscription_id=subscription.id,
                tenant_id=tenant.id,
                amount=subscription.amount,
                currency=subscription.currency,
                status=PaymentStatus.FAILED,
                transaction_type=transaction_type,
                paystack_reference=reference,
                description=f"Failed automatic renewal for {subscription.billing_cycle.value} subscription",
                metadata=metadata,
                failure_reason=charge_result["error"]
            )
            
            self.db.add(payment)
            self.db.commit()
            
            return {
                "subscription_id": subscription.id,
                "success": False,
                "error": charge_result["error"],
                "action": "moved_to_past_due"
            }
    
    def _update_subscription_for_next_period(self, subscription: Subscription) -> None:
        """Update subscription dates for the next billing period"""
        
        now = datetime.utcnow()
        
        if subscription.billing_cycle == BillingCycle.YEARLY:
            next_period_end = subscription.current_period_end + timedelta(days=365)
        else:
            next_period_end = subscription.current_period_end + timedelta(days=30)
        
        subscription.current_period_start = subscription.current_period_end
        subscription.current_period_end = next_period_end
        subscription.ends_at = next_period_end
        
        # If coming from trial, activate the subscription
        if subscription.status == SubscriptionStatus.TRIALING:
            subscription.status = SubscriptionStatus.ACTIVE
    
    def _reset_usage_tracking(self, subscription: Subscription) -> None:
        """Reset usage tracking for new billing period"""
        
        usage = self.db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()
        
        if usage:
            # Update period dates
            usage.period_start = subscription.current_period_start
            usage.period_end = subscription.current_period_end
            
            # Reset monthly counters (keep cumulative API calls)
            usage.monthly_chats_used = 0
            usage.monthly_reset_at = datetime.utcnow()
            
            # Reset daily counters
            usage.daily_chats_used = 0
            usage.daily_reset_at = datetime.utcnow()
    
    def process_grace_period_expirations(self) -> Dict[str, Any]:
        """Process subscriptions whose grace period has expired"""
        
        now = datetime.utcnow()
        
        expired_subscriptions = self.db.query(Subscription).filter(
            and_(
                Subscription.status == SubscriptionStatus.PAST_DUE,
                Subscription.grace_period_ends_at <= now
            )
        ).all()
        
        results = {
            "processed": 0,
            "expired": 0,
            "results": []
        }
        
        for subscription in expired_subscriptions:
            # Expire the subscription
            subscription.status = SubscriptionStatus.EXPIRED
            
            # Update tenant's plan to free tier if available
            tenant = self.db.query(Tenant).filter(Tenant.id == subscription.tenant_id).first()
            if tenant:
                # Find free plan
                from .plan_service import PlanService
                plan_service = PlanService(self.db)
                free_plan = plan_service.get_plan_by_name("Free")
                if free_plan:
                    tenant.plan_id = free_plan.id
            
            results["results"].append({
                "subscription_id": subscription.id,
                "tenant_id": subscription.tenant_id,
                "action": "expired"
            })
            results["processed"] += 1
            results["expired"] += 1
        
        self.db.commit()
        return results
    
    def process_scheduled_cancellations(self) -> Dict[str, Any]:
        """Process subscriptions scheduled for cancellation at period end"""
        
        today = datetime.utcnow().date()
        
        cancelling_subscriptions = self.db.query(Subscription).filter(
            and_(
                Subscription.cancel_at_period_end == True,
                Subscription.current_period_end <= datetime.combine(today, datetime.min.time()) + timedelta(days=1)
            )
        ).all()
        
        results = {
            "processed": 0,
            "cancelled": 0,
            "results": []
        }
        
        for subscription in cancelling_subscriptions:
            # Cancel the subscription
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.cancelled_at = datetime.utcnow()
            subscription.cancel_at_period_end = False
            
            # Update tenant's plan to free tier if available
            tenant = self.db.query(Tenant).filter(Tenant.id == subscription.tenant_id).first()
            if tenant:
                from .plan_service import PlanService
                plan_service = PlanService(self.db)
                free_plan = plan_service.get_plan_by_name("Free")
                if free_plan:
                    tenant.plan_id = free_plan.id
            
            results["results"].append({
                "subscription_id": subscription.id,
                "tenant_id": subscription.tenant_id,
                "action": "cancelled"
            })
            results["processed"] += 1
            results["cancelled"] += 1
        
        self.db.commit()
        return results
    
    def generate_invoices(self) -> Dict[str, Any]:
        """Generate invoices for active subscriptions"""
        
        # Find subscriptions that need invoices (next billing period starting tomorrow)
        tomorrow = datetime.utcnow().date() + timedelta(days=1)
        
        subscriptions_needing_invoices = self.db.query(Subscription).filter(
            and_(
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
                Subscription.current_period_end >= datetime.combine(tomorrow, datetime.min.time()),
                Subscription.current_period_end < datetime.combine(tomorrow, datetime.min.time()) + timedelta(days=1)
            )
        ).all()
        
        results = {
            "processed": 0,
            "generated": 0,
            "results": []
        }
        
        for subscription in subscriptions_needing_invoices:
            # Check if invoice already exists
            existing_invoice = self.db.query(Invoice).filter(
                and_(
                    Invoice.subscription_id == subscription.id,
                    Invoice.period_start == subscription.current_period_start,
                    Invoice.period_end == subscription.current_period_end
                )
            ).first()
            
            if existing_invoice:
                continue
            
            # Generate invoice
            invoice = self._generate_invoice_for_subscription(subscription)
            results["results"].append({
                "subscription_id": subscription.id,
                "invoice_id": invoice.id,
                "amount": float(invoice.total_amount)
            })
            results["processed"] += 1
            results["generated"] += 1
        
        self.db.commit()
        return results
    
    def _generate_invoice_for_subscription(self, subscription: Subscription) -> Invoice:
        """Generate an invoice for a subscription"""
        
        # Generate invoice number
        invoice_number = f"INV-{datetime.utcnow().strftime('%Y%m')}-{uuid.uuid4().hex[:8].upper()}"
        
        # Calculate due date (7 days before period end)
        due_date = subscription.current_period_end - timedelta(days=7)
        
        # Line items
        line_items = [
            {
                "description": f"{subscription.billing_cycle.value.title()} subscription",
                "plan_id": subscription.plan_id,
                "quantity": 1,
                "unit_price": float(subscription.amount),
                "total": float(subscription.amount)
            }
        ]
        
        # Create invoice
        invoice = Invoice(
            subscription_id=subscription.id,
            tenant_id=subscription.tenant_id,
            invoice_number=invoice_number,
            status=PaymentStatus.PENDING,
            subtotal=subscription.amount,
            tax_amount=Decimal("0.00"),  # No tax for now
            total_amount=subscription.amount,
            currency=subscription.currency,
            period_start=subscription.current_period_start,
            period_end=subscription.current_period_end,
            due_date=due_date,
            line_items=line_items
        )
        
        self.db.add(invoice)
        return invoice
    
    def reset_daily_usage_counters(self) -> Dict[str, Any]:
        """Reset daily usage counters for all active subscriptions"""
        
        usage_records = self.db.query(UsageTracking).filter(
            UsageTracking.daily_reset_at < datetime.utcnow().date()
        ).all()
        
        results = {
            "processed": 0,
            "reset": 0
        }
        
        for usage in usage_records:
            usage.daily_chats_used = 0
            usage.daily_reset_at = datetime.utcnow()
            results["processed"] += 1
            results["reset"] += 1
        
        self.db.commit()
        return results
    
    def get_billing_summary(self, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """Get billing summary for a date range"""
        
        # Get payments in date range
        payments = self.db.query(Payment).filter(
            and_(
                Payment.status == PaymentStatus.COMPLETED,
                Payment.processed_at >= start_date,
                Payment.processed_at <= end_date
            )
        ).all()
        
        # Calculate totals
        total_revenue = sum(float(payment.amount) for payment in payments)
        payment_count = len(payments)
        
        # Group by transaction type
        by_type = {}
        for payment in payments:
            trans_type = payment.transaction_type.value
            if trans_type not in by_type:
                by_type[trans_type] = {"count": 0, "revenue": 0}
            by_type[trans_type]["count"] += 1
            by_type[trans_type]["revenue"] += float(payment.amount)
        
        # Group by currency
        by_currency = {}
        for payment in payments:
            currency = payment.currency
            if currency not in by_currency:
                by_currency[currency] = {"count": 0, "revenue": 0}
            by_currency[currency]["count"] += 1
            by_currency[currency]["revenue"] += float(payment.amount)
        
        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "summary": {
                "total_revenue": round(total_revenue, 2),
                "payment_count": payment_count,
                "average_payment": round(total_revenue / max(1, payment_count), 2)
            },
            "by_transaction_type": by_type,
            "by_currency": by_currency
        }
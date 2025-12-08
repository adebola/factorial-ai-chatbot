"""
Analytics and Reporting Service

Provides comprehensive analytics for:
- Revenue metrics (MRR, ARR, growth rate)
- Subscription analytics (active, churned, growth)
- Plan popularity and distribution
- Usage analytics across resources
- Payment success/failure rates
- Churn analysis and retention
"""
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, extract

from ..models.subscription import (
    Subscription,
    SubscriptionStatus,
    Payment,
    PaymentStatus,
    UsageTracking,
    BillingCycle
)
from ..models.plan import Plan
from ..core.logging_config import get_logger

logger = get_logger("analytics-service")


class AnalyticsService:
    """Service for generating analytics and reports"""

    def __init__(self, db: Session):
        self.db = db

    def get_revenue_metrics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate revenue metrics.

        Args:
            start_date: Start date for analysis (default: 30 days ago)
            end_date: End date for analysis (default: now)

        Returns:
            Revenue metrics including MRR, ARR, growth rates
        """
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Calculate MRR (Monthly Recurring Revenue)
        # Sum of all active monthly subscriptions + (yearly subscriptions / 12)
        monthly_subscriptions = self.db.query(
            func.sum(Subscription.amount)
        ).filter(
            and_(
                Subscription.status.in_([
                    SubscriptionStatus.ACTIVE.value,
                    SubscriptionStatus.TRIALING.value
                ]),
                Subscription.billing_cycle == BillingCycle.MONTHLY.value
            )
        ).scalar() or Decimal(0)

        yearly_subscriptions = self.db.query(
            func.sum(Subscription.amount)
        ).filter(
            and_(
                Subscription.status.in_([
                    SubscriptionStatus.ACTIVE.value,
                    SubscriptionStatus.TRIALING.value
                ]),
                Subscription.billing_cycle == BillingCycle.YEARLY.value
            )
        ).scalar() or Decimal(0)

        mrr = monthly_subscriptions + (yearly_subscriptions / 12)
        arr = mrr * 12

        # Calculate total revenue for the period
        total_revenue = self.db.query(
            func.sum(Payment.amount)
        ).filter(
            and_(
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.created_at >= start_date,
                Payment.created_at <= end_date
            )
        ).scalar() or Decimal(0)

        # Calculate revenue from previous period for growth rate
        previous_start = start_date - (end_date - start_date)
        previous_revenue = self.db.query(
            func.sum(Payment.amount)
        ).filter(
            and_(
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.created_at >= previous_start,
                Payment.created_at < start_date
            )
        ).scalar() or Decimal(0)

        # Growth rate
        if previous_revenue > 0:
            growth_rate = ((total_revenue - previous_revenue) / previous_revenue) * 100
        else:
            growth_rate = 100 if total_revenue > 0 else 0

        # Average revenue per user (ARPU)
        active_subscriptions_count = self.db.query(
            func.count(Subscription.id)
        ).filter(
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE.value,
                SubscriptionStatus.TRIALING.value
            ])
        ).scalar() or 0

        arpu = mrr / active_subscriptions_count if active_subscriptions_count > 0 else Decimal(0)

        # Revenue by plan
        revenue_by_plan = self.db.query(
            Plan.name,
            func.sum(Payment.amount).label('revenue')
        ).join(
            Subscription, Subscription.plan_id == Plan.id
        ).join(
            Payment, Payment.subscription_id == Subscription.id
        ).filter(
            and_(
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.created_at >= start_date,
                Payment.created_at <= end_date
            )
        ).group_by(Plan.name).all()

        revenue_breakdown = [
            {"plan": plan_name, "revenue": float(revenue)}
            for plan_name, revenue in revenue_by_plan
        ]

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": (end_date - start_date).days
            },
            "mrr": float(mrr),
            "arr": float(arr),
            "total_revenue": float(total_revenue),
            "previous_period_revenue": float(previous_revenue),
            "growth_rate": float(growth_rate),
            "arpu": float(arpu),
            "active_subscriptions": active_subscriptions_count,
            "revenue_by_plan": revenue_breakdown
        }

    def get_subscription_metrics(self) -> Dict[str, Any]:
        """
        Calculate subscription metrics.

        Returns:
            Subscription counts, growth, and distribution
        """
        # Count by status
        status_counts = self.db.query(
            Subscription.status,
            func.count(Subscription.id).label('count')
        ).group_by(Subscription.status).all()

        status_distribution = {
            status: count for status, count in status_counts
        }

        # Total subscriptions
        total = sum(status_distribution.values())

        # Active subscriptions (ACTIVE + TRIALING)
        active = (
            status_distribution.get(SubscriptionStatus.ACTIVE.value, 0) +
            status_distribution.get(SubscriptionStatus.TRIALING.value, 0)
        )

        # Churned subscriptions (CANCELLED + EXPIRED)
        churned = (
            status_distribution.get(SubscriptionStatus.CANCELLED.value, 0) +
            status_distribution.get(SubscriptionStatus.EXPIRED.value, 0)
        )

        # New subscriptions (last 30 days)
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        new_subscriptions = self.db.query(
            func.count(Subscription.id)
        ).filter(
            Subscription.created_at >= thirty_days_ago
        ).scalar() or 0

        # Subscriptions by plan
        plan_distribution = self.db.query(
            Plan.name,
            func.count(Subscription.id).label('count')
        ).join(
            Subscription, Subscription.plan_id == Plan.id
        ).filter(
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE.value,
                SubscriptionStatus.TRIALING.value
            ])
        ).group_by(Plan.name).all()

        plan_breakdown = [
            {"plan": plan_name, "count": count, "percentage": (count / active * 100) if active > 0 else 0}
            for plan_name, count in plan_distribution
        ]

        # Subscriptions by billing cycle
        cycle_distribution = self.db.query(
            Subscription.billing_cycle,
            func.count(Subscription.id).label('count')
        ).filter(
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE.value,
                SubscriptionStatus.TRIALING.value
            ])
        ).group_by(Subscription.billing_cycle).all()

        cycle_breakdown = {
            cycle: count for cycle, count in cycle_distribution
        }

        # Churn rate (last 30 days)
        subscriptions_30_days_ago = self.db.query(
            func.count(Subscription.id)
        ).filter(
            Subscription.created_at < thirty_days_ago
        ).scalar() or 0

        churned_last_30_days = self.db.query(
            func.count(Subscription.id)
        ).filter(
            and_(
                Subscription.cancelled_at >= thirty_days_ago,
                Subscription.status.in_([
                    SubscriptionStatus.CANCELLED.value,
                    SubscriptionStatus.EXPIRED.value
                ])
            )
        ).scalar() or 0

        churn_rate = (churned_last_30_days / subscriptions_30_days_ago * 100) if subscriptions_30_days_ago > 0 else 0

        return {
            "total_subscriptions": total,
            "active_subscriptions": active,
            "churned_subscriptions": churned,
            "new_subscriptions_30d": new_subscriptions,
            "churn_rate_30d": float(churn_rate),
            "status_distribution": status_distribution,
            "plan_distribution": plan_breakdown,
            "billing_cycle_distribution": cycle_breakdown
        }

    def get_usage_analytics(self) -> Dict[str, Any]:
        """
        Calculate usage analytics across all resources.

        Returns:
            Usage statistics for documents, websites, and chats
        """
        # Get all usage tracking records for active subscriptions
        usage_stats = self.db.query(
            func.sum(UsageTracking.documents_used).label('total_documents'),
            func.sum(UsageTracking.websites_used).label('total_websites'),
            func.sum(UsageTracking.monthly_chats_used).label('total_monthly_chats'),
            func.avg(UsageTracking.documents_used).label('avg_documents'),
            func.avg(UsageTracking.websites_used).label('avg_websites'),
            func.avg(UsageTracking.monthly_chats_used).label('avg_monthly_chats'),
            func.count(UsageTracking.id).label('active_users')
        ).join(
            Subscription, Subscription.id == UsageTracking.subscription_id
        ).filter(
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE.value,
                SubscriptionStatus.TRIALING.value
            ])
        ).first()

        # Usage by plan
        usage_by_plan = self.db.query(
            Plan.name,
            func.avg(UsageTracking.documents_used).label('avg_documents'),
            func.avg(UsageTracking.websites_used).label('avg_websites'),
            func.avg(UsageTracking.monthly_chats_used).label('avg_monthly_chats'),
            func.count(UsageTracking.id).label('user_count')
        ).join(
            Subscription, Subscription.id == UsageTracking.subscription_id
        ).join(
            Plan, Plan.id == Subscription.plan_id
        ).filter(
            Subscription.status.in_([
                SubscriptionStatus.ACTIVE.value,
                SubscriptionStatus.TRIALING.value
            ])
        ).group_by(Plan.name).all()

        usage_breakdown = [
            {
                "plan": plan_name,
                "avg_documents": float(avg_docs or 0),
                "avg_websites": float(avg_sites or 0),
                "avg_monthly_chats": float(avg_chats or 0),
                "user_count": user_count
            }
            for plan_name, avg_docs, avg_sites, avg_chats, user_count in usage_by_plan
        ]

        # Users at capacity (100% usage)
        at_capacity = self.db.query(
            func.count(UsageTracking.id)
        ).join(
            Subscription, Subscription.id == UsageTracking.subscription_id
        ).join(
            Plan, Plan.id == Subscription.plan_id
        ).filter(
            and_(
                Subscription.status.in_([
                    SubscriptionStatus.ACTIVE.value,
                    SubscriptionStatus.TRIALING.value
                ]),
                or_(
                    UsageTracking.documents_used >= Plan.document_limit,
                    UsageTracking.websites_used >= Plan.website_limit,
                    UsageTracking.monthly_chats_used >= Plan.monthly_chat_limit
                )
            )
        ).scalar() or 0

        return {
            "total_usage": {
                "documents": int(usage_stats.total_documents or 0),
                "websites": int(usage_stats.total_websites or 0),
                "monthly_chats": int(usage_stats.total_monthly_chats or 0)
            },
            "average_usage": {
                "documents": float(usage_stats.avg_documents or 0),
                "websites": float(usage_stats.avg_websites or 0),
                "monthly_chats": float(usage_stats.avg_monthly_chats or 0)
            },
            "active_users": usage_stats.active_users or 0,
            "users_at_capacity": at_capacity,
            "usage_by_plan": usage_breakdown
        }

    def get_payment_analytics(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculate payment success/failure rates and trends.

        Args:
            start_date: Start date for analysis (default: 30 days ago)
            end_date: End date for analysis (default: now)

        Returns:
            Payment statistics and trends
        """
        if not end_date:
            end_date = datetime.now(timezone.utc)
        if not start_date:
            start_date = end_date - timedelta(days=30)

        # Payment counts by status
        payment_stats = self.db.query(
            Payment.status,
            func.count(Payment.id).label('count'),
            func.sum(Payment.amount).label('total_amount')
        ).filter(
            and_(
                Payment.created_at >= start_date,
                Payment.created_at <= end_date
            )
        ).group_by(Payment.status).all()

        status_breakdown = {
            status: {"count": count, "amount": float(total or 0)}
            for status, count, total in payment_stats
        }

        # Calculate success rate
        total_payments = sum(item["count"] for item in status_breakdown.values())
        successful_payments = status_breakdown.get(PaymentStatus.COMPLETED.value, {}).get("count", 0)
        success_rate = (successful_payments / total_payments * 100) if total_payments > 0 else 0

        # Failed payments
        failed_payments = status_breakdown.get(PaymentStatus.FAILED.value, {}).get("count", 0)
        failure_rate = (failed_payments / total_payments * 100) if total_payments > 0 else 0

        # Average payment amount
        avg_payment = self.db.query(
            func.avg(Payment.amount)
        ).filter(
            and_(
                Payment.status == PaymentStatus.COMPLETED.value,
                Payment.created_at >= start_date,
                Payment.created_at <= end_date
            )
        ).scalar() or Decimal(0)

        # Payments over time (daily)
        daily_payments = self.db.query(
            func.date(Payment.created_at).label('date'),
            func.count(Payment.id).label('count'),
            func.sum(case(
                (Payment.status == PaymentStatus.COMPLETED.value, Payment.amount),
                else_=0
            )).label('revenue')
        ).filter(
            and_(
                Payment.created_at >= start_date,
                Payment.created_at <= end_date
            )
        ).group_by(func.date(Payment.created_at)).order_by('date').all()

        payment_timeline = [
            {
                "date": date.isoformat(),
                "count": count,
                "revenue": float(revenue or 0)
            }
            for date, count, revenue in daily_payments
        ]

        return {
            "period": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "total_payments": total_payments,
            "successful_payments": successful_payments,
            "failed_payments": failed_payments,
            "success_rate": float(success_rate),
            "failure_rate": float(failure_rate),
            "average_payment_amount": float(avg_payment),
            "status_breakdown": status_breakdown,
            "payment_timeline": payment_timeline
        }

    def get_churn_analysis(self) -> Dict[str, Any]:
        """
        Analyze churn patterns and reasons.

        Returns:
            Churn analysis including reasons, timing, and recovery potential
        """
        # Churn by time period
        now = datetime.now(timezone.utc)
        periods = [
            ("last_7_days", now - timedelta(days=7)),
            ("last_30_days", now - timedelta(days=30)),
            ("last_90_days", now - timedelta(days=90))
        ]

        churn_by_period = {}
        for period_name, start_date in periods:
            churned = self.db.query(
                func.count(Subscription.id)
            ).filter(
                and_(
                    Subscription.cancelled_at >= start_date,
                    Subscription.status.in_([
                        SubscriptionStatus.CANCELLED.value,
                        SubscriptionStatus.EXPIRED.value
                    ])
                )
            ).scalar() or 0

            total_at_start = self.db.query(
                func.count(Subscription.id)
            ).filter(
                Subscription.created_at < start_date
            ).scalar() or 0

            churn_rate = (churned / total_at_start * 100) if total_at_start > 0 else 0

            churn_by_period[period_name] = {
                "churned_count": churned,
                "churn_rate": float(churn_rate)
            }

        # Churn reasons (from cancellation_reason field)
        churn_reasons = self.db.query(
            Subscription.cancellation_reason,
            func.count(Subscription.id).label('count')
        ).filter(
            and_(
                Subscription.status.in_([
                    SubscriptionStatus.CANCELLED.value,
                    SubscriptionStatus.EXPIRED.value
                ]),
                Subscription.cancellation_reason.isnot(None)
            )
        ).group_by(Subscription.cancellation_reason).all()

        reasons_breakdown = [
            {"reason": reason or "Not specified", "count": count}
            for reason, count in churn_reasons
        ]

        # Churn by plan
        churn_by_plan = self.db.query(
            Plan.name,
            func.count(Subscription.id).label('churned_count')
        ).join(
            Subscription, Subscription.plan_id == Plan.id
        ).filter(
            Subscription.status.in_([
                SubscriptionStatus.CANCELLED.value,
                SubscriptionStatus.EXPIRED.value
            ])
        ).group_by(Plan.name).all()

        plan_breakdown = [
            {"plan": plan_name, "churned_count": count}
            for plan_name, count in churn_by_plan
        ]

        # Average subscription lifetime before churn
        avg_lifetime = self.db.query(
            func.avg(
                extract('epoch', Subscription.cancelled_at - Subscription.created_at) / 86400
            )
        ).filter(
            and_(
                Subscription.cancelled_at.isnot(None),
                Subscription.status.in_([
                    SubscriptionStatus.CANCELLED.value,
                    SubscriptionStatus.EXPIRED.value
                ])
            )
        ).scalar() or 0

        # Potential recovery (subscriptions cancelled but can be reactivated)
        recoverable = self.db.query(
            func.count(Subscription.id)
        ).filter(
            and_(
                Subscription.cancel_at_period_end == True,
                Subscription.current_period_end > now
            )
        ).scalar() or 0

        return {
            "churn_by_period": churn_by_period,
            "churn_reasons": reasons_breakdown,
            "churn_by_plan": plan_breakdown,
            "average_subscription_lifetime_days": float(avg_lifetime),
            "recoverable_subscriptions": recoverable
        }

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive dashboard summary with key metrics.

        Returns:
            All key metrics in one response
        """
        revenue = self.get_revenue_metrics()
        subscriptions = self.get_subscription_metrics()
        usage = self.get_usage_analytics()
        payments = self.get_payment_analytics()
        churn = self.get_churn_analysis()

        return {
            "revenue": {
                "mrr": revenue["mrr"],
                "arr": revenue["arr"],
                "growth_rate": revenue["growth_rate"],
                "arpu": revenue["arpu"]
            },
            "subscriptions": {
                "total": subscriptions["total_subscriptions"],
                "active": subscriptions["active_subscriptions"],
                "new_30d": subscriptions["new_subscriptions_30d"],
                "churn_rate_30d": subscriptions["churn_rate_30d"]
            },
            "usage": {
                "active_users": usage["active_users"],
                "users_at_capacity": usage["users_at_capacity"],
                "total_chats": usage["total_usage"]["monthly_chats"]
            },
            "payments": {
                "success_rate": payments["success_rate"],
                "total_payments": payments["total_payments"],
                "avg_payment": payments["average_payment_amount"]
            },
            "churn": {
                "churn_rate_30d": churn["churn_by_period"]["last_30_days"]["churn_rate"],
                "recoverable": churn["recoverable_subscriptions"],
                "avg_lifetime_days": churn["average_subscription_lifetime_days"]
            }
        }

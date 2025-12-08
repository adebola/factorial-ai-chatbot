"""
Analytics and reporting API endpoints.

This module provides endpoints for business intelligence and analytics:
- Revenue reporting (MRR, ARR, growth rates)
- Subscription metrics (churn, plan distribution)
- Usage analytics (resource consumption)
- Payment analytics (success rates, trends)
- Churn analysis (patterns, reasons)
"""
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..services.dependencies import TokenClaims, require_admin
from ..services.analytics_service import AnalyticsService

router = APIRouter(prefix="/analytics", tags=["analytics"])


def verify_admin_user(claims: TokenClaims = Depends(require_admin)) -> TokenClaims:
    """
    Verify that the current user is an admin.

    Analytics endpoints are restricted to admin users only for security
    and business intelligence protection.
    """
    # require_admin already checks is_admin, so just return claims
    return claims


@router.get("/revenue")
def get_revenue_metrics(
    start_date: Optional[datetime] = Query(None, description="Start date for revenue analysis"),
    end_date: Optional[datetime] = Query(None, description="End date for revenue analysis"),
    claims: TokenClaims = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get revenue metrics including MRR, ARR, and growth rates.

    **Admin Only**

    Returns:
    - **mrr**: Monthly Recurring Revenue
    - **arr**: Annual Recurring Revenue
    - **growth_rate**: MRR growth rate vs previous period
    - **arpu**: Average Revenue Per User
    - **revenue_by_plan**: Breakdown by subscription plan
    - **previous_period**: Comparison data

    Example Response:
    ```json
    {
        "mrr": 15000.00,
        "arr": 180000.00,
        "growth_rate": 12.5,
        "arpu": 29.99,
        "revenue_by_plan": {
            "Basic": {"mrr": 5000.00, "count": 250},
            "Pro": {"mrr": 8000.00, "count": 267}
        },
        "previous_period": {
            "mrr": 13333.33,
            "growth_rate": 12.5
        }
    }
    ```
    """
    analytics_service = AnalyticsService(db)

    try:
        metrics = analytics_service.get_revenue_metrics(
            start_date=start_date,
            end_date=end_date
        )
        return metrics
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate revenue metrics: {str(e)}"
        )


@router.get("/subscriptions")
def get_subscription_metrics(
    claims: TokenClaims = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get subscription metrics including status distribution and churn.

    **Admin Only**

    Returns:
    - **total_subscriptions**: Total count of all subscriptions
    - **active_subscriptions**: Currently active subscriptions
    - **trialing_subscriptions**: Subscriptions in trial period
    - **cancelled_subscriptions**: Cancelled subscriptions
    - **expired_subscriptions**: Expired subscriptions
    - **churn_rate_30d**: 30-day churn rate percentage
    - **plan_distribution**: Breakdown by plan
    - **status_distribution**: Breakdown by status

    Example Response:
    ```json
    {
        "total_subscriptions": 1000,
        "active_subscriptions": 750,
        "trialing_subscriptions": 100,
        "cancelled_subscriptions": 50,
        "expired_subscriptions": 100,
        "churn_rate_30d": 3.5,
        "plan_distribution": {
            "Free": 200,
            "Basic": 400,
            "Pro": 300,
            "Enterprise": 100
        },
        "status_distribution": {
            "ACTIVE": 750,
            "TRIALING": 100,
            "CANCELLED": 50
        }
    }
    ```
    """
    analytics_service = AnalyticsService(db)

    try:
        metrics = analytics_service.get_subscription_metrics()
        return metrics
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate subscription metrics: {str(e)}"
        )


@router.get("/usage")
def get_usage_analytics(
    claims: TokenClaims = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get usage analytics across all resources.

    **Admin Only**

    Returns:
    - **total_usage**: Aggregate usage across all subscriptions
    - **average_usage**: Average usage per subscription
    - **active_users**: Users with non-zero usage
    - **users_at_capacity**: Users at or near limits
    - **usage_by_plan**: Usage breakdown by plan

    Resources tracked:
    - Documents uploaded
    - Websites ingested
    - Monthly chat messages

    Example Response:
    ```json
    {
        "total_usage": {
            "documents": 15000,
            "websites": 2500,
            "monthly_chats": 450000
        },
        "average_usage": {
            "documents": 20.0,
            "websites": 3.3,
            "monthly_chats": 600.0
        },
        "active_users": 650,
        "users_at_capacity": {
            "documents": 45,
            "websites": 23,
            "monthly_chats": 78
        },
        "usage_by_plan": {
            "Basic": {
                "avg_documents": 15.5,
                "avg_websites": 2.1,
                "avg_monthly_chats": 1200.0
            }
        }
    }
    ```
    """
    analytics_service = AnalyticsService(db)

    try:
        analytics = analytics_service.get_usage_analytics()
        return analytics
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate usage analytics: {str(e)}"
        )


@router.get("/payments")
def get_payment_analytics(
    start_date: Optional[datetime] = Query(
        default=None,
        description="Start date for payment analysis (defaults to 30 days ago)"
    ),
    end_date: Optional[datetime] = Query(
        default=None,
        description="End date for payment analysis (defaults to now)"
    ),
    claims: TokenClaims = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get payment analytics including success rates and trends.

    **Admin Only**

    Returns:
    - **total_payments**: Total payment attempts
    - **successful_payments**: Successfully completed payments
    - **failed_payments**: Failed payment attempts
    - **success_rate**: Success rate percentage
    - **total_revenue**: Total revenue from successful payments
    - **average_payment**: Average payment amount
    - **payment_timeline**: Daily breakdown of payments and revenue

    Example Response:
    ```json
    {
        "total_payments": 500,
        "successful_payments": 475,
        "failed_payments": 25,
        "success_rate": 95.0,
        "total_revenue": 142500.00,
        "average_payment": 300.00,
        "payment_timeline": [
            {
                "date": "2025-11-01",
                "count": 15,
                "revenue": 4500.00
            }
        ]
    }
    ```
    """
    analytics_service = AnalyticsService(db)

    # Default to last 30 days if not specified
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        analytics = analytics_service.get_payment_analytics(
            start_date=start_date,
            end_date=end_date
        )
        return analytics
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate payment analytics: {str(e)}"
        )


@router.get("/churn")
def get_churn_analysis(
    claims: TokenClaims = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get churn analysis including patterns and reasons.

    **Admin Only**

    Returns:
    - **churn_by_period**: Monthly churn breakdown
    - **churn_by_plan**: Churn rate by subscription plan
    - **average_lifetime_days**: Average subscription lifetime before churn
    - **total_churned**: Total churned subscriptions
    - **recoverable_subscriptions**: Subscriptions scheduled for cancellation (can be recovered)
    - **churn_reasons**: Breakdown by cancellation reason (if tracked)

    Example Response:
    ```json
    {
        "churn_by_period": {
            "last_7_days": {"count": 5, "rate": 1.2},
            "last_30_days": {"count": 18, "rate": 3.5},
            "last_90_days": {"count": 45, "rate": 8.2}
        },
        "churn_by_plan": {
            "Basic": {"churned": 12, "rate": 4.8},
            "Pro": {"churned": 6, "rate": 2.0}
        },
        "average_lifetime_days": 245.5,
        "total_churned": 150,
        "recoverable_subscriptions": 8,
        "churn_reasons": {
            "too_expensive": 45,
            "not_enough_value": 32,
            "switching_provider": 28
        }
    }
    ```
    """
    analytics_service = AnalyticsService(db)

    try:
        analysis = analytics_service.get_churn_analysis()
        return analysis
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to perform churn analysis: {str(e)}"
        )


@router.get("/dashboard")
def get_dashboard_summary(
    claims: TokenClaims = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """
    Get comprehensive dashboard summary with key metrics.

    **Admin Only**

    This endpoint provides a consolidated view of all key business metrics
    for display on an admin dashboard. It combines data from revenue,
    subscriptions, usage, and payment analytics.

    Returns:
    - **revenue**: MRR, ARR, and growth rate
    - **subscriptions**: Total, active, and churn rate
    - **usage**: Active users and capacity utilization
    - **payments**: Success rate and recent performance
    - **alerts**: Important notifications (high churn, low conversion, etc.)

    Example Response:
    ```json
    {
        "revenue": {
            "mrr": 15000.00,
            "arr": 180000.00,
            "growth_rate": 12.5
        },
        "subscriptions": {
            "total": 1000,
            "active": 750,
            "churn_rate_30d": 3.5
        },
        "usage": {
            "active_users": 650,
            "users_at_capacity": {
                "documents": 45,
                "websites": 23,
                "monthly_chats": 78
            }
        },
        "payments": {
            "success_rate": 95.0,
            "last_7_days": {
                "count": 105,
                "revenue": 31500.00
            }
        },
        "alerts": [
            {
                "type": "warning",
                "message": "Churn rate increased by 15% this month"
            },
            {
                "type": "info",
                "message": "78 users approaching monthly chat limit"
            }
        ]
    }
    ```
    """
    analytics_service = AnalyticsService(db)

    try:
        summary = analytics_service.get_dashboard_summary()
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate dashboard summary: {str(e)}"
        )


@router.get("/export/csv")
def export_analytics_csv(
    metric_type: str = Query(
        ...,
        description="Type of metric to export: revenue, subscriptions, usage, payments, churn"
    ),
    start_date: Optional[datetime] = Query(None, description="Start date for export"),
    end_date: Optional[datetime] = Query(None, description="End date for export"),
    claims: TokenClaims = Depends(verify_admin_user),
    db: Session = Depends(get_db)
):
    """
    Export analytics data as CSV.

    **Admin Only**

    Supports exporting:
    - revenue: Revenue metrics over time
    - subscriptions: Subscription details
    - usage: Usage statistics
    - payments: Payment transaction history
    - churn: Churned subscription details

    Returns CSV file download.

    **Note**: Implementation pending - requires CSV generation library.
    """
    # TODO: Implement CSV export functionality
    # This would require adding python-csv or pandas dependency
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="CSV export functionality coming soon"
    )

"""
Feature flag middleware for plan-based access control.

This module provides decorators and middleware to enforce plan feature flags,
ensuring tenants can only access features included in their subscription plan.
"""

from functools import wraps
from typing import Callable, List, Optional
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ..services.dependencies import TokenClaims
from ..services.plan_service import PlanService
from ..services.subscription_service import SubscriptionService


class FeatureFlag:
    """Enum-like class for feature flag names"""
    SENTIMENT_ANALYSIS = "has_sentiment_analysis"
    CONVERSATIONAL_WORKFLOW = "has_conversational_workflow"
    API_ACCESS = "has_api_access"
    CUSTOM_INTEGRATIONS = "has_custom_integrations"
    ON_PREMISE = "has_on_premise"


def require_feature(feature_flag: str):
    """
    Decorator to require a specific feature flag for endpoint access.

    Usage:
        @router.get("/sentiment-analysis")
        @require_feature(FeatureFlag.SENTIMENT_ANALYSIS)
        async def analyze_sentiment(claims: TokenClaims = Depends(validate_token)):
            # Implementation
            pass

    Args:
        feature_flag: The feature flag to check (e.g., "has_sentiment_analysis")

    Raises:
        HTTPException: 403 if the tenant's plan doesn't include the feature
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract claims and db from kwargs
            claims: Optional[TokenClaims] = kwargs.get('claims')
            db: Optional[Session] = kwargs.get('db')

            if not claims or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Missing authentication claims or database session"
                )

            # Check if tenant has access to the feature
            if not await check_feature_access(claims.tenant_id, feature_flag, db):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Your current plan does not include access to this feature. Please upgrade your plan."
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_any_feature(*feature_flags: str):
    """
    Decorator to require at least one of multiple feature flags.

    Usage:
        @router.get("/advanced-analytics")
        @require_any_feature(FeatureFlag.SENTIMENT_ANALYSIS, FeatureFlag.CONVERSATIONAL_WORKFLOW)
        async def advanced_analytics(claims: TokenClaims = Depends(validate_token)):
            # Implementation
            pass

    Args:
        *feature_flags: Multiple feature flags (requires at least one)

    Raises:
        HTTPException: 403 if the tenant's plan doesn't include any of the features
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            claims: Optional[TokenClaims] = kwargs.get('claims')
            db: Optional[Session] = kwargs.get('db')

            if not claims or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Missing authentication claims or database session"
                )

            # Check if tenant has access to any of the features
            has_access = False
            for feature_flag in feature_flags:
                if await check_feature_access(claims.tenant_id, feature_flag, db):
                    has_access = True
                    break

            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Your current plan does not include access to this feature. Please upgrade your plan."
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_all_features(*feature_flags: str):
    """
    Decorator to require all of multiple feature flags.

    Usage:
        @router.get("/enterprise-api")
        @require_all_features(FeatureFlag.API_ACCESS, FeatureFlag.CUSTOM_INTEGRATIONS)
        async def enterprise_api(claims: TokenClaims = Depends(validate_token)):
            # Implementation
            pass

    Args:
        *feature_flags: Multiple feature flags (requires all)

    Raises:
        HTTPException: 403 if the tenant's plan doesn't include all features
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            claims: Optional[TokenClaims] = kwargs.get('claims')
            db: Optional[Session] = kwargs.get('db')

            if not claims or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Missing authentication claims or database session"
                )

            # Check if tenant has access to all features
            for feature_flag in feature_flags:
                if not await check_feature_access(claims.tenant_id, feature_flag, db):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Your current plan does not include all required features. Please upgrade your plan."
                    )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


async def check_feature_access(tenant_id: str, feature_flag: str, db: Session) -> bool:
    """
    Check if a tenant has access to a specific feature based on their plan.

    Args:
        tenant_id: The tenant's UUID
        feature_flag: The feature flag to check (e.g., "has_sentiment_analysis")
        db: Database session

    Returns:
        bool: True if the tenant has access, False otherwise
    """
    try:
        subscription_service = SubscriptionService(db)
        plan_service = PlanService(db)

        # Get tenant's current subscription
        subscription = subscription_service.get_subscription_by_tenant(tenant_id)
        if not subscription:
            return False

        # Get plan details
        plan = plan_service.get_plan_by_id(subscription.plan_id)
        if not plan:
            return False

        # Check if the plan has the feature flag enabled
        feature_value = getattr(plan, feature_flag, False)
        return bool(feature_value)

    except Exception:
        # Default to denying access if there's an error
        return False


async def get_tenant_features(tenant_id: str, db: Session) -> dict:
    """
    Get all feature flags for a tenant's current plan.

    Args:
        tenant_id: The tenant's UUID
        db: Database session

    Returns:
        dict: Dictionary of feature flags and their values
    """
    try:
        subscription_service = SubscriptionService(db)
        plan_service = PlanService(db)

        # Get tenant's current subscription
        subscription = subscription_service.get_subscription_by_tenant(tenant_id)
        if not subscription:
            return {
                "has_sentiment_analysis": False,
                "has_conversational_workflow": False,
                "has_api_access": False,
                "has_custom_integrations": False,
                "has_on_premise": False,
                "analytics_level": "basic"
            }

        # Get plan details
        plan = plan_service.get_plan_by_id(subscription.plan_id)
        if not plan:
            return {
                "has_sentiment_analysis": False,
                "has_conversational_workflow": False,
                "has_api_access": False,
                "has_custom_integrations": False,
                "has_on_premise": False,
                "analytics_level": "basic"
            }

        return {
            "has_sentiment_analysis": plan.has_sentiment_analysis,
            "has_conversational_workflow": plan.has_conversational_workflow,
            "has_api_access": plan.has_api_access,
            "has_custom_integrations": plan.has_custom_integrations,
            "has_on_premise": plan.has_on_premise,
            "analytics_level": plan.analytics_level,
            "support_channels": plan.support_channels
        }

    except Exception:
        # Default to basic features if there's an error
        return {
            "has_sentiment_analysis": False,
            "has_conversational_workflow": False,
            "has_api_access": False,
            "has_custom_integrations": False,
            "has_on_premise": False,
            "analytics_level": "basic"
        }

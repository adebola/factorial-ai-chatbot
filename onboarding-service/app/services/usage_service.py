from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from decimal import Decimal

from sqlalchemy.orm import Session
from sqlalchemy import and_

from ..models.tenant import Tenant, Plan
from ..models.subscription import (
    Subscription, SubscriptionStatus, UsageTracking
)
from .subscription_service import SubscriptionService
from .plan_service import PlanService


class UsageService:
    """Service for tracking and enforcing usage limits"""
    
    def __init__(self, db: Session):
        self.db = db
        self.subscription_service = SubscriptionService(db)
        self.plan_service = PlanService(db)
    
    def check_usage_limit(
        self,
        tenant_id: str,
        usage_type: str,
        amount: int = 1
    ) -> Dict[str, Any]:
        """Check if tenant can perform an action based on usage limits"""
        
        # Get active subscription
        subscription = self.subscription_service.get_subscription_by_tenant(tenant_id)
        if not subscription:
            return {
                "allowed": False,
                "reason": "No active subscription found",
                "current_usage": 0,
                "limit": 0,
                "remaining": 0
            }
        
        # Check subscription status
        if subscription.status not in [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]:
            return {
                "allowed": False,
                "reason": f"Subscription is {subscription.status.value}",
                "current_usage": 0,
                "limit": 0,
                "remaining": 0
            }
        
        # Get plan limits
        plan = self.plan_service.get_plan_by_id(subscription.plan_id)
        if not plan:
            return {
                "allowed": False,
                "reason": "Plan not found",
                "current_usage": 0,
                "limit": 0,
                "remaining": 0
            }
        
        # Get usage tracking
        usage = self._get_or_create_usage_tracking(subscription)
        
        # Check specific limit
        if usage_type == "documents":
            current = usage.documents_used
            limit = plan.document_limit
            allowed = current + amount <= limit
        elif usage_type == "websites":
            current = usage.websites_used
            limit = plan.website_limit
            allowed = current + amount <= limit
        elif usage_type == "daily_chats":
            current = usage.daily_chats_used
            limit = plan.daily_chat_limit
            allowed = current + amount <= limit
        elif usage_type == "monthly_chats":
            current = usage.monthly_chats_used
            limit = plan.monthly_chat_limit
            allowed = current + amount <= limit
        elif usage_type == "api_calls":
            # API calls are typically unlimited
            current = usage.api_calls_made
            limit = -1  # Unlimited
            allowed = True
        else:
            return {
                "allowed": False,
                "reason": f"Unknown usage type: {usage_type}",
                "current_usage": 0,
                "limit": 0,
                "remaining": 0
            }
        
        return {
            "allowed": allowed,
            "reason": None if allowed else f"{usage_type.replace('_', ' ').title()} limit would be exceeded",
            "current_usage": current,
            "limit": limit,
            "remaining": max(0, limit - current) if limit > 0 else -1
        }
    
    def increment_usage(
        self,
        tenant_id: str,
        usage_type: str,
        amount: int = 1,
        check_limit: bool = True
    ) -> Dict[str, Any]:
        """Increment usage counter with optional limit checking"""
        
        if check_limit:
            # Check if usage is allowed
            limit_check = self.check_usage_limit(tenant_id, usage_type, amount)
            if not limit_check["allowed"]:
                return {
                    "success": False,
                    "error": limit_check["reason"],
                    "limit_check": limit_check
                }
        
        # Get subscription and usage tracking
        subscription = self.subscription_service.get_subscription_by_tenant(tenant_id)
        if not subscription:
            return {
                "success": False,
                "error": "No active subscription found"
            }
        
        usage = self._get_or_create_usage_tracking(subscription)
        
        # Check if daily/monthly counters need reset
        self._reset_counters_if_needed(usage)
        
        # Increment the appropriate counter
        old_value = 0
        if usage_type == "documents":
            old_value = usage.documents_used
            usage.documents_used += amount
        elif usage_type == "websites":
            old_value = usage.websites_used
            usage.websites_used += amount
        elif usage_type == "daily_chats":
            old_value = usage.daily_chats_used
            usage.daily_chats_used += amount
        elif usage_type == "monthly_chats":
            old_value = usage.monthly_chats_used
            usage.monthly_chats_used += amount
        elif usage_type == "api_calls":
            old_value = usage.api_calls_made
            usage.api_calls_made += amount
        else:
            return {
                "success": False,
                "error": f"Unknown usage type: {usage_type}"
            }
        
        usage.updated_at = datetime.utcnow()
        self.db.commit()
        
        return {
            "success": True,
            "usage_type": usage_type,
            "old_value": old_value,
            "new_value": old_value + amount,
            "amount_added": amount
        }
    
    def get_usage_statistics(self, tenant_id: str) -> Dict[str, Any]:
        """Get comprehensive usage statistics for a tenant"""
        
        subscription = self.subscription_service.get_subscription_by_tenant(tenant_id)
        if not subscription:
            return {
                "error": "No active subscription found"
            }
        
        plan = self.plan_service.get_plan_by_id(subscription.plan_id)
        if not plan:
            return {
                "error": "Plan not found"
            }
        
        usage = self._get_or_create_usage_tracking(subscription)
        
        # Reset counters if needed
        self._reset_counters_if_needed(usage)
        
        # Calculate percentages
        doc_percentage = (usage.documents_used / plan.document_limit * 100) if plan.document_limit > 0 else 0
        website_percentage = (usage.websites_used / plan.website_limit * 100) if plan.website_limit > 0 else 0
        daily_chat_percentage = (usage.daily_chats_used / plan.daily_chat_limit * 100) if plan.daily_chat_limit > 0 else 0
        monthly_chat_percentage = (usage.monthly_chats_used / plan.monthly_chat_limit * 100) if plan.monthly_chat_limit > 0 else 0
        
        return {
            "tenant_id": tenant_id,
            "subscription_id": subscription.id,
            "plan_name": plan.name,
            "billing_period": {
                "start": usage.period_start.isoformat(),
                "end": usage.period_end.isoformat(),
                "days_remaining": (usage.period_end - datetime.utcnow()).days
            },
            "usage": {
                "documents": {
                    "used": usage.documents_used,
                    "limit": plan.document_limit,
                    "remaining": max(0, plan.document_limit - usage.documents_used),
                    "percentage": round(doc_percentage, 2),
                    "unlimited": plan.document_limit <= 0
                },
                "websites": {
                    "used": usage.websites_used,
                    "limit": plan.website_limit,
                    "remaining": max(0, plan.website_limit - usage.websites_used),
                    "percentage": round(website_percentage, 2),
                    "unlimited": plan.website_limit <= 0
                },
                "daily_chats": {
                    "used": usage.daily_chats_used,
                    "limit": plan.daily_chat_limit,
                    "remaining": max(0, plan.daily_chat_limit - usage.daily_chats_used),
                    "percentage": round(daily_chat_percentage, 2),
                    "unlimited": plan.daily_chat_limit <= 0,
                    "resets_at": self._next_daily_reset().isoformat()
                },
                "monthly_chats": {
                    "used": usage.monthly_chats_used,
                    "limit": plan.monthly_chat_limit,
                    "remaining": max(0, plan.monthly_chat_limit - usage.monthly_chats_used),
                    "percentage": round(monthly_chat_percentage, 2),
                    "unlimited": plan.monthly_chat_limit <= 0,
                    "resets_at": usage.period_end.isoformat()
                },
                "api_calls": {
                    "used": usage.api_calls_made,
                    "unlimited": True
                }
            },
            "warnings": self._get_usage_warnings(usage, plan)
        }
    
    def reset_usage_for_billing_period(self, subscription_id: str) -> Dict[str, Any]:
        """Reset usage counters for a new billing period"""
        
        subscription = self.subscription_service.get_subscription_by_id(subscription_id)
        if not subscription:
            return {
                "success": False,
                "error": "Subscription not found"
            }
        
        usage = self._get_or_create_usage_tracking(subscription)
        
        # Reset monthly counters
        usage.monthly_chats_used = 0
        usage.monthly_reset_at = datetime.utcnow()
        
        # Reset daily counters
        usage.daily_chats_used = 0
        usage.daily_reset_at = datetime.utcnow()
        
        # Update billing period
        usage.period_start = subscription.current_period_start
        usage.period_end = subscription.current_period_end
        
        # Note: Documents and websites are NOT reset as they're cumulative
        
        usage.updated_at = datetime.utcnow()
        self.db.commit()
        
        return {
            "success": True,
            "subscription_id": subscription_id,
            "new_period_start": usage.period_start.isoformat(),
            "new_period_end": usage.period_end.isoformat()
        }
    
    def _get_or_create_usage_tracking(self, subscription: Subscription) -> UsageTracking:
        """Get or create usage tracking record for subscription"""
        
        usage = self.db.query(UsageTracking).filter(
            UsageTracking.subscription_id == subscription.id
        ).first()
        
        if not usage:
            usage = UsageTracking(
                tenant_id=subscription.tenant_id,
                subscription_id=subscription.id,
                period_start=subscription.current_period_start,
                period_end=subscription.current_period_end
            )
            self.db.add(usage)
            self.db.commit()
            self.db.refresh(usage)
        
        return usage
    
    def _reset_counters_if_needed(self, usage: UsageTracking) -> None:
        """Reset daily counters if a day has passed"""
        
        now = datetime.utcnow()
        
        # Reset daily counters if needed
        if not usage.daily_reset_at or usage.daily_reset_at.date() < now.date():
            usage.daily_chats_used = 0
            usage.daily_reset_at = now
            self.db.commit()
    
    def _next_daily_reset(self) -> datetime:
        """Calculate next daily reset time"""
        now = datetime.utcnow()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return tomorrow
    
    def _get_usage_warnings(self, usage: UsageTracking, plan: Plan) -> List[Dict[str, Any]]:
        """Get usage warnings for near-limit usage"""
        
        warnings = []
        
        # Document usage warning (80% threshold)
        if plan.document_limit > 0:
            doc_percentage = (usage.documents_used / plan.document_limit) * 100
            if doc_percentage >= 80:
                warnings.append({
                    "type": "documents",
                    "message": f"Document usage at {doc_percentage:.1f}% of limit",
                    "severity": "high" if doc_percentage >= 95 else "medium"
                })
        
        # Website usage warning (80% threshold)
        if plan.website_limit > 0:
            web_percentage = (usage.websites_used / plan.website_limit) * 100
            if web_percentage >= 80:
                warnings.append({
                    "type": "websites",
                    "message": f"Website usage at {web_percentage:.1f}% of limit",
                    "severity": "high" if web_percentage >= 95 else "medium"
                })
        
        # Daily chat usage warning (90% threshold)
        if plan.daily_chat_limit > 0:
            daily_percentage = (usage.daily_chats_used / plan.daily_chat_limit) * 100
            if daily_percentage >= 90:
                warnings.append({
                    "type": "daily_chats",
                    "message": f"Daily chat usage at {daily_percentage:.1f}% of limit",
                    "severity": "high" if daily_percentage >= 98 else "medium"
                })
        
        # Monthly chat usage warning (85% threshold)
        if plan.monthly_chat_limit > 0:
            monthly_percentage = (usage.monthly_chats_used / plan.monthly_chat_limit) * 100
            if monthly_percentage >= 85:
                warnings.append({
                    "type": "monthly_chats",
                    "message": f"Monthly chat usage at {monthly_percentage:.1f}% of limit",
                    "severity": "high" if monthly_percentage >= 95 else "medium"
                })
        
        return warnings
    
    def get_tenant_usage_summary(self, tenant_id: str) -> Dict[str, Any]:
        """Get a summary of usage for dashboard display"""
        
        stats = self.get_usage_statistics(tenant_id)
        if "error" in stats:
            return stats
        
        usage = stats["usage"]
        
        return {
            "summary": {
                "documents_used": usage["documents"]["used"],
                "documents_percentage": usage["documents"]["percentage"],
                "websites_used": usage["websites"]["used"],
                "websites_percentage": usage["websites"]["percentage"],
                "daily_chats_used": usage["daily_chats"]["used"],
                "daily_chats_percentage": usage["daily_chats"]["percentage"],
                "monthly_chats_used": usage["monthly_chats"]["used"],
                "monthly_chats_percentage": usage["monthly_chats"]["percentage"]
            },
            "status": {
                "has_warnings": len(stats["warnings"]) > 0,
                "warning_count": len(stats["warnings"]),
                "highest_usage_type": self._get_highest_usage_type(usage),
                "days_remaining": stats["billing_period"]["days_remaining"]
            },
            "quick_limits": {
                "can_add_document": usage["documents"]["remaining"] > 0 or usage["documents"]["unlimited"],
                "can_add_website": usage["websites"]["remaining"] > 0 or usage["websites"]["unlimited"],
                "can_chat_today": usage["daily_chats"]["remaining"] > 0 or usage["daily_chats"]["unlimited"],
                "can_chat_this_month": usage["monthly_chats"]["remaining"] > 0 or usage["monthly_chats"]["unlimited"]
            }
        }
    
    def _get_highest_usage_type(self, usage: Dict[str, Any]) -> str:
        """Get the usage type with the highest percentage"""
        
        percentages = {
            "documents": usage["documents"]["percentage"],
            "websites": usage["websites"]["percentage"],
            "daily_chats": usage["daily_chats"]["percentage"],
            "monthly_chats": usage["monthly_chats"]["percentage"]
        }
        
        return max(percentages, key=percentages.get)
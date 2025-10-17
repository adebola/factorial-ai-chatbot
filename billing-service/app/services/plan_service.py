from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional, Dict, Any
from datetime import datetime
from decimal import Decimal

from ..models.plan import Plan
from ..core.config import settings


class PlanService:
    """Service for managing subscription plans"""

    def __init__(self, db: Session):
        self.db = db

    def create_plan(
        self,
        name: str,
        description: Optional[str] = None,
        document_limit: int = 10,
        website_limit: int = 1,
        daily_chat_limit: int = 50,
        monthly_chat_limit: int = 1500,
        monthly_plan_cost: Decimal = Decimal('0.00'),
        yearly_plan_cost: Decimal = Decimal('0.00'),
        features: Optional[Dict[str, Any]] = None
    ) -> Plan:
        """Create a new plan"""

        # Check if the plan name already exists (including soft deleted)
        existing_plan = self.db.query(Plan).filter(Plan.name == name).first()
        if existing_plan and not existing_plan.is_deleted:
            raise ValueError(f"Plan with name '{name}' already exists")
        elif existing_plan and existing_plan.is_deleted:
            raise ValueError(f"Plan with name '{name}' exists but is deleted. Consider undeleting it instead.")

        plan = Plan(
            name=name,
            description=description,
            document_limit=document_limit,
            website_limit=website_limit,
            daily_chat_limit=daily_chat_limit,
            monthly_chat_limit=monthly_chat_limit,
            monthly_plan_cost=monthly_plan_cost,
            yearly_plan_cost=yearly_plan_cost,
            features=features or {},
            is_active=True,
            is_deleted=False
        )

        self.db.add(plan)
        self.db.commit()
        self.db.refresh(plan)

        return plan

    def get_plan_by_id(self, plan_id: str, include_deleted: bool = False) -> Optional[Plan]:
        """Get plan by ID"""
        query = self.db.query(Plan).filter(Plan.id == plan_id)

        if not include_deleted:
            query = query.filter(Plan.is_deleted == False)

        return query.first()

    def get_plan_by_name(self, name: str, include_deleted: bool = False) -> Optional[Plan]:
        """Get plan by name"""
        query = self.db.query(Plan).filter(Plan.name == name)

        if not include_deleted:
            query = query.filter(Plan.is_deleted == False)

        return query.first()

    def get_all_plans(self, include_deleted: bool = False, active_only: bool = False) -> List[Plan]:
        """Get all plans"""
        query = self.db.query(Plan)

        if not include_deleted:
            query = query.filter(Plan.is_deleted == False)

        if active_only:
            query = query.filter(Plan.is_active == True)

        return query.order_by(Plan.monthly_plan_cost, Plan.name).all()

    def update_plan(
        self,
        plan_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        document_limit: Optional[int] = None,
        website_limit: Optional[int] = None,
        daily_chat_limit: Optional[int] = None,
        monthly_chat_limit: Optional[int] = None,
        monthly_plan_cost: Optional[Decimal] = None,
        yearly_plan_cost: Optional[Decimal] = None,
        features: Optional[Dict[str, Any]] = None,
        is_active: Optional[bool] = None
    ) -> Optional[Plan]:
        """Update an existing plan"""

        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return None

        # Check if new name conflicts with existing plan
        if name and name != plan.name:
            existing_plan = self.get_plan_by_name(name)
            if existing_plan:
                raise ValueError(f"Plan with name '{name}' already exists")

        # Update fields
        if name is not None:
            plan.name = name
        if description is not None:
            plan.description = description
        if document_limit is not None:
            plan.document_limit = document_limit
        if website_limit is not None:
            plan.website_limit = website_limit
        if daily_chat_limit is not None:
            plan.daily_chat_limit = daily_chat_limit
        if monthly_chat_limit is not None:
            plan.monthly_chat_limit = monthly_chat_limit
        if monthly_plan_cost is not None:
            plan.monthly_plan_cost = monthly_plan_cost
        if yearly_plan_cost is not None:
            plan.yearly_plan_cost = yearly_plan_cost
        if features is not None:
            plan.features = features
        if is_active is not None:
            plan.is_active = is_active

        plan.updated_at = datetime.utcnow()

        self.db.commit()
        self.db.refresh(plan)

        return plan

    def soft_delete_plan(self, plan_id: str) -> bool:
        """Soft delete a plan"""
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return False

        # Note: Tenant relationship removed - plan deletion temporarily allowed
        # TODO: Implement tenant count check via OAuth2 server API when needed
        # For now, we'll allow plan deletion since tenant management is in OAuth2 server

        plan.is_deleted = True
        plan.deleted_at = datetime.utcnow()
        plan.is_active = False

        self.db.commit()

        return True

    def restore_plan(self, plan_id: str) -> bool:
        """Restore a soft-deleted plan"""
        plan = self.get_plan_by_id(plan_id, include_deleted=True)
        if not plan or not plan.is_deleted:
            return False

        plan.is_deleted = False
        plan.deleted_at = None
        plan.is_active = True

        self.db.commit()

        return True

    def get_plan_usage_stats(self, plan_id: str) -> Dict[str, Any]:
        """Get usage statistics for a plan"""
        plan = self.get_plan_by_id(plan_id)
        if not plan:
            return {}

        # Note: Tenant statistics temporarily unavailable
        # TODO: Implement tenant count via OAuth2 server API calls

        return {
            "plan_id": plan.id,
            "plan_name": plan.name,
            "active_tenant_count": 0,  # Placeholder - tenant data in OAuth2 server
            "total_tenant_count": 0,   # Placeholder - tenant data in OAuth2 server
            "is_deletable": True,      # Temporarily allowing deletion
            "note": "Tenant statistics unavailable - tenant management moved to OAuth2 server"
        }

    def create_default_plans(self) -> List[Plan]:
        """Create default plans if they don't exist"""
        default_plans = [
            {
                "name": "Free",
                "description": "Basic plan with limited features",
                "document_limit": 5,
                "website_limit": 1,
                "daily_chat_limit": 10,
                "monthly_chat_limit": 300,
                "monthly_plan_cost": Decimal('0.00'),
                "yearly_plan_cost": Decimal('0.00'),
                "features": {
                    "support": "community",
                    "api_access": False,
                    "priority_support": False
                }
            },
            {
                "name": "Basic",
                "description": "Perfect for small teams and personal use",
                "document_limit": 25,
                "website_limit": 3,
                "daily_chat_limit": 100,
                "monthly_chat_limit": 3000,
                "monthly_plan_cost": Decimal('9.99'),
                "yearly_plan_cost": Decimal('99.99'),
                "features": {
                    "support": "email",
                    "api_access": True,
                    "priority_support": False
                }
            },
            {
                "name": "Pro",
                "description": "Advanced features for growing businesses",
                "document_limit": 100,
                "website_limit": 10,
                "daily_chat_limit": 500,
                "monthly_chat_limit": 15000,
                "monthly_plan_cost": Decimal('29.99'),
                "yearly_plan_cost": Decimal('299.99'),
                "features": {
                    "support": "priority",
                    "api_access": True,
                    "priority_support": True,
                    "analytics": True
                }
            },
            {
                "name": "Enterprise",
                "description": "Unlimited access for large organizations",
                "document_limit": 1000,
                "website_limit": 50,
                "daily_chat_limit": 2000,
                "monthly_chat_limit": 60000,
                "monthly_plan_cost": Decimal('99.99'),
                "yearly_plan_cost": Decimal('999.99'),
                "features": {
                    "support": "dedicated",
                    "api_access": True,
                    "priority_support": True,
                    "analytics": True,
                    "custom_integrations": True,
                    "sso": True
                }
            }
        ]

        created_plans = []
        for plan_data in default_plans:
            existing = self.get_plan_by_name(plan_data["name"])
            if not existing:
                plan = self.create_plan(**plan_data)
                created_plans.append(plan)

        return created_plans

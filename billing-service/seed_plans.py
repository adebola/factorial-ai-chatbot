"""Seed default plans into billing service database"""
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add app to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models.plan import Plan
from app.core.database import Base

# Get database URL from environment
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5432/billing_db")

print(f"Connecting to: {DATABASE_URL}")

# Create engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)
session = SessionLocal()

# Default plans
default_plans = [
    {
        "id": "a45a17b2-44ed-40e0-ad52-2689b9d56ca9",
        "name": "Free",
        "description": "Perfect for trying out FactorialBot",
        "document_limit": 5,
        "website_limit": 1,
        "daily_chat_limit": 10,
        "monthly_chat_limit": 300,
        "monthly_plan_cost": 0.00,
        "yearly_plan_cost": 0.00,
        "is_active": True,
        "features": {"items": ["5 documents", "1 website", "300 monthly chats", "Email support"]}
    },
    {
        "id": "b56b28c3-55fe-51f1-be63-3790cab67daa",
        "name": "Basic",
        "description": "For small businesses getting started",
        "document_limit": 25,
        "website_limit": 3,
        "daily_chat_limit": 100,
        "monthly_chat_limit": 3000,
        "monthly_plan_cost": 9.99,
        "yearly_plan_cost": 99.00,
        "is_active": True,
        "features": {"items": ["25 documents", "3 websites", "3000 monthly chats", "Priority support"]}
    },
    {
        "id": "c67c39d4-66ef-62e2-cf74-4801dbc78ebb",
        "name": "Pro",
        "description": "For growing businesses",
        "document_limit": 100,
        "website_limit": 10,
        "daily_chat_limit": 500,
        "monthly_chat_limit": 15000,
        "monthly_plan_cost": 29.99,
        "yearly_plan_cost": 299.00,
        "is_active": True,
        "features": {"items": ["100 documents", "10 websites", "15000 monthly chats", "Priority support", "Custom branding"]}
    },
    {
        "id": "d78d40e5-77fg-73f3-dg85-5912ecd89fcc",
        "name": "Enterprise",
        "description": "For large organizations",
        "document_limit": 1000,
        "website_limit": 50,
        "daily_chat_limit": 2000,
        "monthly_chat_limit": 60000,
        "monthly_plan_cost": 99.99,
        "yearly_plan_cost": 999.00,
        "is_active": True,
        "features": {"items": ["1000 documents", "50 websites", "60000 monthly chats", "Dedicated support", "Custom branding", "SLA"]}
    }
]

try:
    # Check if plans already exist
    existing_count = session.query(Plan).count()
    if existing_count > 0:
        print(f"Database already has {existing_count} plans. Skipping seed.")
        sys.exit(0)
    
    # Create plans
    for plan_data in default_plans:
        plan = Plan(**plan_data)
        session.add(plan)
        print(f"Created plan: {plan.name}")
    
    session.commit()
    print(f"\nSuccessfully seeded {len(default_plans)} plans!")
    
except Exception as e:
    session.rollback()
    print(f"Error seeding plans: {e}")
    sys.exit(1)
finally:
    session.close()

#!/usr/bin/env python3
"""
Backfill Usage Data

This script queries the actual source databases (chatbot_db, onboard_db) and populates
the usage_tracking table in billing_db with the real usage counts.

Usage:
    python backfill_usage.py
"""
import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import os
from sqlalchemy import create_engine, text
from datetime import datetime, timezone
from app.core.database import SessionLocal
from app.models.subscription import UsageTracking, Subscription

def backfill_usage():
    """Backfill usage data from source databases"""

    # Connect to billing database
    billing_db = SessionLocal()

    # Connect to source databases
    chatbot_engine = create_engine("postgresql://postgres:password@localhost:5432/chatbot_db")
    onboard_engine = create_engine("postgresql://postgres:password@localhost:5432/onboard_db")

    try:
        print("=" * 80)
        print("BACKFILLING USAGE DATA")
        print("=" * 80)
        print()

        # Get all subscriptions
        subscriptions = billing_db.query(Subscription).all()
        print(f"Found {len(subscriptions)} subscriptions to process")
        print()

        for subscription in subscriptions:
            tenant_id = subscription.tenant_id
            print(f"Processing tenant: {tenant_id}")

            # Get usage tracking record
            usage = billing_db.query(UsageTracking).filter(
                UsageTracking.subscription_id == subscription.id
            ).first()

            if not usage:
                print(f"  ⚠️  No usage tracking record found, skipping")
                continue

            # Query daily chat messages (today only)
            with chatbot_engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM chat_messages
                        WHERE tenant_id = :tenant_id
                        AND created_at >= CURRENT_DATE
                    """),
                    {"tenant_id": tenant_id}
                )
                daily_chat_count = result.scalar()

            # Query monthly chat messages (this month)
            with chatbot_engine.connect() as conn:
                result = conn.execute(
                    text("""
                        SELECT COUNT(*)
                        FROM chat_messages
                        WHERE tenant_id = :tenant_id
                        AND created_at >= DATE_TRUNC('month', CURRENT_TIMESTAMP)
                    """),
                    {"tenant_id": tenant_id}
                )
                monthly_chat_count = result.scalar()

            # Query documents count (all time)
            with onboard_engine.connect() as conn:
                result = conn.execute(
                    text("SELECT COUNT(*) FROM documents WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id}
                )
                doc_count = result.scalar()

            # Query websites count (all time)
            with onboard_engine.connect() as conn:
                result = conn.execute(
                    text("SELECT COUNT(*) FROM website_ingestions WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id}
                )
                website_count = result.scalar()

            # Update usage tracking
            old_values = {
                "documents": usage.documents_used,
                "websites": usage.websites_used,
                "daily_chats": usage.daily_chats_used,
                "monthly_chats": usage.monthly_chats_used
            }

            usage.documents_used = doc_count
            usage.websites_used = website_count
            usage.daily_chats_used = daily_chat_count
            usage.monthly_chats_used = monthly_chat_count
            usage.updated_at = datetime.now(timezone.utc)

            billing_db.commit()

            print(f"  ✓ Updated usage:")
            print(f"    - Documents: {old_values['documents']} → {doc_count}")
            print(f"    - Websites: {old_values['websites']} → {website_count}")
            print(f"    - Daily Chats: {old_values['daily_chats']} → {daily_chat_count}")
            print(f"    - Monthly Chats: {old_values['monthly_chats']} → {monthly_chat_count}")
            print()

        print("=" * 80)
        print("BACKFILL COMPLETE")
        print("=" * 80)

    except Exception as e:
        print(f"❌ Error during backfill: {e}")
        import traceback
        traceback.print_exc()
        billing_db.rollback()
    finally:
        billing_db.close()
        chatbot_engine.dispose()
        onboard_engine.dispose()

if __name__ == "__main__":
    backfill_usage()

#!/usr/bin/env python3
"""
Backfill Usage Statistics Script

This script synchronizes existing documents, websites, and chat usage from
the onboarding and chat services into the billing service's UsageTracking table.

Usage:
    python backfill-usage-statistics.py [--tenant-id TENANT_ID] [--dry-run]

Environment Variables Required:
    - ONBOARDING_DB_URL: PostgreSQL URL for onboarding service database
    - BILLING_DB_URL: PostgreSQL URL for billing service database
    - CHAT_DB_URL: PostgreSQL URL for chat database (chatbot_db)

Examples:
    # Backfill all tenants
    python backfill-usage-statistics.py

    # Backfill specific tenant (dry run)
    python backfill-usage-statistics.py --tenant-id 9eb23c01-b66a-4e23-8316-4884532d5b04 --dry-run

    # Backfill specific tenant (apply changes)
    python backfill-usage-statistics.py --tenant-id 9eb23c01-b66a-4e23-8316-4884532d5b04
"""

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker, Session
except ImportError:
    print("Error: SQLAlchemy not installed")
    print("Install with: pip install sqlalchemy psycopg2-binary")
    sys.exit(1)


class UsageBackfill:
    """Backfill usage statistics from onboarding/chat databases to billing database"""

    def __init__(self, onboarding_db_url: str, billing_db_url: str, chat_db_url: str, dry_run: bool = False):
        self.onboarding_engine = create_engine(onboarding_db_url)
        self.billing_engine = create_engine(billing_db_url)
        self.chat_engine = create_engine(chat_db_url)
        self.dry_run = dry_run

        self.OnboardingSession = sessionmaker(bind=self.onboarding_engine)
        self.BillingSession = sessionmaker(bind=self.billing_engine)
        self.ChatSession = sessionmaker(bind=self.chat_engine)

    def get_tenant_document_count(self, tenant_id: str) -> int:
        """Get count of documents for a tenant from onboarding database"""
        with self.OnboardingSession() as session:
            result = session.execute(
                text("""
                    SELECT COUNT(*) as count
                    FROM documents
                    WHERE tenant_id = :tenant_id
                      AND status = 'COMPLETED'
                """),
                {"tenant_id": tenant_id}
            )
            row = result.fetchone()
            return row[0] if row else 0

    def get_tenant_website_count(self, tenant_id: str) -> int:
        """Get count of websites for a tenant from onboarding database"""
        with self.OnboardingSession() as session:
            result = session.execute(
                text("""
                    SELECT COUNT(*) as count
                    FROM website_ingestions
                    WHERE tenant_id = :tenant_id
                      AND status IN ('COMPLETED', 'IN_PROGRESS')
                """),
                {"tenant_id": tenant_id}
            )
            row = result.fetchone()
            return row[0] if row else 0

    def get_tenant_chat_counts(self, tenant_id: str) -> Dict[str, int]:
        """Get chat message counts for a tenant from chat database"""
        with self.ChatSession() as session:
            # Get total monthly chats (all time for now - could be filtered by date)
            result = session.execute(
                text("""
                    SELECT COUNT(*) as count
                    FROM chat_messages
                    WHERE tenant_id = :tenant_id
                      AND message_type = 'user'
                """),
                {"tenant_id": tenant_id}
            )
            row = result.fetchone()
            monthly_count = row[0] if row else 0

            # Get today's chats for daily count
            result = session.execute(
                text("""
                    SELECT COUNT(*) as count
                    FROM chat_messages
                    WHERE tenant_id = :tenant_id
                      AND message_type = 'user'
                      AND DATE(created_at) = CURRENT_DATE
                """),
                {"tenant_id": tenant_id}
            )
            row = result.fetchone()
            daily_count = row[0] if row else 0

            return {
                "daily": daily_count,
                "monthly": monthly_count
            }

    def get_all_tenant_ids(self) -> List[str]:
        """Get all tenant IDs from billing service subscriptions"""
        with self.BillingSession() as session:
            result = session.execute(
                text("""
                    SELECT DISTINCT tenant_id
                    FROM subscriptions
                    WHERE status != 'cancelled'
                    ORDER BY created_at
                """)
            )
            return [row[0] for row in result.fetchall()]

    def get_subscription_and_usage(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get subscription and current usage tracking for a tenant"""
        with self.BillingSession() as session:
            result = session.execute(
                text("""
                    SELECT
                        s.id as subscription_id,
                        s.plan_id,
                        s.status,
                        u.id as usage_id,
                        u.documents_used,
                        u.websites_used,
                        u.daily_chats_used,
                        u.monthly_chats_used
                    FROM subscriptions s
                    LEFT JOIN usage_tracking u ON u.subscription_id = s.id
                    WHERE s.tenant_id = :tenant_id
                      AND s.status != 'cancelled'
                    ORDER BY s.created_at DESC
                    LIMIT 1
                """),
                {"tenant_id": tenant_id}
            )
            row = result.fetchone()
            if not row:
                return None

            return {
                "subscription_id": row[0],
                "plan_id": row[1],
                "status": row[2],
                "usage_id": row[3],
                "documents_used": row[4] or 0,
                "websites_used": row[5] or 0,
                "daily_chats_used": row[6] or 0,
                "monthly_chats_used": row[7] or 0
            }

    def update_usage_tracking(
        self,
        subscription_id: str,
        documents: int,
        websites: int,
        daily_chats: int,
        monthly_chats: int
    ) -> bool:
        """Update or create usage tracking record"""
        try:
            with self.BillingSession() as session:
                # Check if usage tracking exists
                result = session.execute(
                    text("SELECT id FROM usage_tracking WHERE subscription_id = :sub_id"),
                    {"sub_id": subscription_id}
                )
                exists = result.fetchone() is not None

                if exists:
                    # Update existing
                    session.execute(
                        text("""
                            UPDATE usage_tracking
                            SET documents_used = :docs,
                                websites_used = :websites,
                                daily_chats_used = :daily,
                                monthly_chats_used = :monthly,
                                updated_at = :now
                            WHERE subscription_id = :sub_id
                        """),
                        {
                            "docs": documents,
                            "websites": websites,
                            "daily": daily_chats,
                            "monthly": monthly_chats,
                            "now": datetime.now(timezone.utc),
                            "sub_id": subscription_id
                        }
                    )
                else:
                    # Create new
                    from datetime import timedelta
                    now = datetime.now(timezone.utc)
                    session.execute(
                        text("""
                            INSERT INTO usage_tracking (
                                id, subscription_id, documents_used, websites_used,
                                daily_chats_used, monthly_chats_used,
                                daily_reset_at, monthly_reset_at,
                                period_start, period_end,
                                created_at, updated_at
                            ) VALUES (
                                gen_random_uuid(), :sub_id, :docs, :websites,
                                :daily, :monthly,
                                :daily_reset, :monthly_reset,
                                :period_start, :period_end,
                                :now, :now
                            )
                        """),
                        {
                            "sub_id": subscription_id,
                            "docs": documents,
                            "websites": websites,
                            "daily": daily_chats,
                            "monthly": monthly_chats,
                            "daily_reset": now + timedelta(days=1),
                            "monthly_reset": now + timedelta(days=30),
                            "period_start": now,
                            "period_end": now + timedelta(days=30),
                            "now": now
                        }
                    )

                session.commit()
                return True

        except Exception as e:
            print(f"Error updating usage tracking: {e}")
            return False

    def backfill_tenant(self, tenant_id: str) -> Dict[str, Any]:
        """Backfill usage statistics for a single tenant"""
        print(f"\n{'='*80}")
        print(f"Processing tenant: {tenant_id}")
        print(f"{'='*80}")

        # Get subscription info
        sub_info = self.get_subscription_and_usage(tenant_id)
        if not sub_info:
            print(f"❌ No active subscription found for tenant {tenant_id}")
            return {"tenant_id": tenant_id, "status": "no_subscription"}

        print(f"\n📋 Current Billing Data:")
        print(f"   Subscription ID: {sub_info['subscription_id']}")
        print(f"   Plan ID: {sub_info['plan_id']}")
        print(f"   Status: {sub_info['status']}")
        print(f"   Documents: {sub_info['documents_used']}")
        print(f"   Websites: {sub_info['websites_used']}")
        print(f"   Daily Chats: {sub_info['daily_chats_used']}")
        print(f"   Monthly Chats: {sub_info['monthly_chats_used']}")

        # Get actual counts from source databases
        print(f"\n🔍 Querying actual usage from source databases...")
        doc_count = self.get_tenant_document_count(tenant_id)
        website_count = self.get_tenant_website_count(tenant_id)
        chat_counts = self.get_tenant_chat_counts(tenant_id)

        print(f"\n📊 Actual Usage Found:")
        print(f"   Documents: {doc_count}")
        print(f"   Websites: {website_count}")
        print(f"   Daily Chats: {chat_counts['daily']}")
        print(f"   Monthly Chats: {chat_counts['monthly']}")

        # Check if update needed
        needs_update = (
            doc_count != sub_info['documents_used'] or
            website_count != sub_info['websites_used'] or
            chat_counts['daily'] != sub_info['daily_chats_used'] or
            chat_counts['monthly'] != sub_info['monthly_chats_used']
        )

        if not needs_update:
            print(f"\n✅ Usage statistics already accurate - no update needed")
            return {"tenant_id": tenant_id, "status": "up_to_date"}

        # Update usage
        print(f"\n{'📝 DRY RUN - Would update:' if self.dry_run else '💾 Updating usage tracking:'}")
        print(f"   Documents: {sub_info['documents_used']} → {doc_count}")
        print(f"   Websites: {sub_info['websites_used']} → {website_count}")
        print(f"   Daily Chats: {sub_info['daily_chats_used']} → {chat_counts['daily']}")
        print(f"   Monthly Chats: {sub_info['monthly_chats_used']} → {chat_counts['monthly']}")

        if not self.dry_run:
            success = self.update_usage_tracking(
                sub_info['subscription_id'],
                doc_count,
                website_count,
                chat_counts['daily'],
                chat_counts['monthly']
            )
            if success:
                print(f"\n✅ Successfully updated usage statistics")
                return {"tenant_id": tenant_id, "status": "updated"}
            else:
                print(f"\n❌ Failed to update usage statistics")
                return {"tenant_id": tenant_id, "status": "failed"}
        else:
            return {"tenant_id": tenant_id, "status": "dry_run"}

    def run(self, tenant_id: Optional[str] = None):
        """Run the backfill process"""
        print("\n" + "="*80)
        print("USAGE STATISTICS BACKFILL SCRIPT")
        print("="*80)
        if self.dry_run:
            print("⚠️  DRY RUN MODE - No changes will be made")
        print()

        if tenant_id:
            # Backfill single tenant
            result = self.backfill_tenant(tenant_id)
            print(f"\n{'='*80}")
            print(f"Result: {result['status']}")
        else:
            # Backfill all tenants
            tenant_ids = self.get_all_tenant_ids()
            print(f"Found {len(tenant_ids)} tenants with active subscriptions\n")

            results = []
            for tid in tenant_ids:
                result = self.backfill_tenant(tid)
                results.append(result)

            # Summary
            print(f"\n{'='*80}")
            print("BACKFILL SUMMARY")
            print(f"{'='*80}")
            print(f"Total tenants processed: {len(results)}")
            print(f"Updated: {len([r for r in results if r['status'] == 'updated'])}")
            print(f"Already up-to-date: {len([r for r in results if r['status'] == 'up_to_date'])}")
            print(f"No subscription: {len([r for r in results if r['status'] == 'no_subscription'])}")
            print(f"Failed: {len([r for r in results if r['status'] == 'failed'])}")
            if self.dry_run:
                print(f"Dry run: {len([r for r in results if r['status'] == 'dry_run'])}")

        print(f"\n{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(description="Backfill usage statistics from source databases to billing service")
    parser.add_argument("--tenant-id", help="Specific tenant ID to backfill (optional, backfills all if not provided)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without applying them")
    parser.add_argument(
        "--onboarding-db",
        default=os.environ.get("ONBOARDING_DB_URL"),
        help="Onboarding database URL (default: ONBOARDING_DB_URL env var)"
    )
    parser.add_argument(
        "--billing-db",
        default=os.environ.get("BILLING_DB_URL"),
        help="Billing database URL (default: BILLING_DB_URL env var)"
    )
    parser.add_argument(
        "--chat-db",
        default=os.environ.get("CHAT_DB_URL"),
        help="Chat database URL (default: CHAT_DB_URL env var)"
    )

    args = parser.parse_args()

    # Validate database URLs
    if not args.onboarding_db:
        print("Error: ONBOARDING_DB_URL environment variable not set or --onboarding-db not provided")
        sys.exit(1)
    if not args.billing_db:
        print("Error: BILLING_DB_URL environment variable not set or --billing-db not provided")
        sys.exit(1)
    if not args.chat_db:
        print("Error: CHAT_DB_URL environment variable not set or --chat-db not provided")
        sys.exit(1)

    # Run backfill
    backfill = UsageBackfill(
        onboarding_db_url=args.onboarding_db,
        billing_db_url=args.billing_db,
        chat_db_url=args.chat_db,
        dry_run=args.dry_run
    )

    backfill.run(tenant_id=args.tenant_id)


if __name__ == "__main__":
    main()

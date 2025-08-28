from datetime import datetime, timedelta
import asyncio
import logging
from typing import Dict, Any

from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

from ..core.config import settings
from ..services.billing_service import BillingService

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class BillingTaskScheduler:
    """Scheduler for automated billing tasks"""
    
    def __init__(self):
        self.db_session = SessionLocal()
        self.billing_service = BillingService(self.db_session)
    
    def __del__(self):
        if hasattr(self, 'db_session'):
            self.db_session.close()
    
    async def run_daily_billing_tasks(self) -> Dict[str, Any]:
        """Run all daily billing tasks"""
        
        logger.info("Starting daily billing tasks...")
        start_time = datetime.utcnow()
        
        results = {
            "start_time": start_time.isoformat(),
            "tasks": {}
        }
        
        try:
            # 1. Process subscription renewals
            logger.info("Processing subscription renewals...")
            renewal_results = await self.billing_service.process_renewals()
            results["tasks"]["renewals"] = renewal_results
            logger.info(f"Renewals processed: {renewal_results['successful']} successful, {renewal_results['failed']} failed")
            
            # 2. Process grace period expirations
            logger.info("Processing grace period expirations...")
            grace_results = self.billing_service.process_grace_period_expirations()
            results["tasks"]["grace_expirations"] = grace_results
            logger.info(f"Grace period expirations: {grace_results['expired']} subscriptions expired")
            
            # 3. Process scheduled cancellations
            logger.info("Processing scheduled cancellations...")
            cancellation_results = self.billing_service.process_scheduled_cancellations()
            results["tasks"]["cancellations"] = cancellation_results
            logger.info(f"Scheduled cancellations: {cancellation_results['cancelled']} subscriptions cancelled")
            
            # 4. Generate invoices
            logger.info("Generating invoices...")
            invoice_results = self.billing_service.generate_invoices()
            results["tasks"]["invoices"] = invoice_results
            logger.info(f"Invoices generated: {invoice_results['generated']} new invoices")
            
            # 5. Reset daily usage counters
            logger.info("Resetting daily usage counters...")
            usage_reset_results = self.billing_service.reset_daily_usage_counters()
            results["tasks"]["usage_reset"] = usage_reset_results
            logger.info(f"Daily usage reset: {usage_reset_results['reset']} records updated")
            
            end_time = datetime.utcnow()
            results["end_time"] = end_time.isoformat()
            results["duration_seconds"] = (end_time - start_time).total_seconds()
            results["success"] = True
            
            logger.info(f"Daily billing tasks completed in {results['duration_seconds']:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Daily billing tasks failed: {str(e)}")
            results["success"] = False
            results["error"] = str(e)
            results["end_time"] = datetime.utcnow().isoformat()
        
        finally:
            self.db_session.close()
        
        return results
    
    async def run_hourly_billing_tasks(self) -> Dict[str, Any]:
        """Run hourly billing tasks (lighter operations)"""
        
        logger.info("Starting hourly billing tasks...")
        start_time = datetime.utcnow()
        
        results = {
            "start_time": start_time.isoformat(),
            "tasks": {}
        }
        
        try:
            # Check for immediate payment verifications needed
            # This could be expanded to handle webhooks that failed processing
            
            # For now, just a placeholder
            results["tasks"]["webhook_retries"] = {"processed": 0, "successful": 0}
            
            end_time = datetime.utcnow()
            results["end_time"] = end_time.isoformat()
            results["duration_seconds"] = (end_time - start_time).total_seconds()
            results["success"] = True
            
            logger.info(f"Hourly billing tasks completed in {results['duration_seconds']:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Hourly billing tasks failed: {str(e)}")
            results["success"] = False
            results["error"] = str(e)
            results["end_time"] = datetime.utcnow().isoformat()
        
        finally:
            self.db_session.close()
        
        return results
    
    async def run_weekly_billing_tasks(self) -> Dict[str, Any]:
        """Run weekly billing tasks (analytics and cleanup)"""
        
        logger.info("Starting weekly billing tasks...")
        start_time = datetime.utcnow()
        
        results = {
            "start_time": start_time.isoformat(),
            "tasks": {}
        }
        
        try:
            # Generate weekly billing summary
            week_start = start_time - timedelta(days=7)
            billing_summary = self.billing_service.get_billing_summary(week_start, start_time)
            results["tasks"]["weekly_summary"] = billing_summary
            
            logger.info(f"Weekly revenue: {billing_summary['summary']['total_revenue']}")
            
            # Clean up old webhook records (older than 30 days)
            from ..models.subscription import PaystackWebhook
            thirty_days_ago = start_time - timedelta(days=30)
            
            old_webhooks = self.db_session.query(PaystackWebhook).filter(
                PaystackWebhook.received_at < thirty_days_ago
            ).count()
            
            self.db_session.query(PaystackWebhook).filter(
                PaystackWebhook.received_at < thirty_days_ago
            ).delete()
            
            self.db_session.commit()
            
            results["tasks"]["cleanup"] = {
                "old_webhooks_deleted": old_webhooks
            }
            
            end_time = datetime.utcnow()
            results["end_time"] = end_time.isoformat()
            results["duration_seconds"] = (end_time - start_time).total_seconds()
            results["success"] = True
            
            logger.info(f"Weekly billing tasks completed in {results['duration_seconds']:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Weekly billing tasks failed: {str(e)}")
            results["success"] = False
            results["error"] = str(e)
            results["end_time"] = datetime.utcnow().isoformat()
        
        finally:
            self.db_session.close()
        
        return results


# Standalone functions for running tasks

async def run_daily_billing():
    """Standalone function to run daily billing tasks"""
    scheduler = BillingTaskScheduler()
    return await scheduler.run_daily_billing_tasks()


async def run_hourly_billing():
    """Standalone function to run hourly billing tasks"""
    scheduler = BillingTaskScheduler()
    return await scheduler.run_hourly_billing_tasks()


async def run_weekly_billing():
    """Standalone function to run weekly billing tasks"""
    scheduler = BillingTaskScheduler()
    return await scheduler.run_weekly_billing_tasks()


# CLI functions for manual execution

def run_daily_billing_sync():
    """Synchronous wrapper for daily billing tasks"""
    return asyncio.run(run_daily_billing())


def run_hourly_billing_sync():
    """Synchronous wrapper for hourly billing tasks"""
    return asyncio.run(run_hourly_billing())


def run_weekly_billing_sync():
    """Synchronous wrapper for weekly billing tasks"""
    return asyncio.run(run_weekly_billing())


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        task_type = sys.argv[1]
        
        if task_type == "daily":
            result = run_daily_billing_sync()
            print(f"Daily billing task result: {result}")
        elif task_type == "hourly":
            result = run_hourly_billing_sync()
            print(f"Hourly billing task result: {result}")
        elif task_type == "weekly":
            result = run_weekly_billing_sync()
            print(f"Weekly billing task result: {result}")
        else:
            print("Usage: python billing_tasks.py [daily|hourly|weekly]")
    else:
        print("Usage: python billing_tasks.py [daily|hourly|weekly]")


# Cron job examples:
# Daily at 2 AM: 0 2 * * * cd /path/to/project && python -m app.tasks.billing_tasks daily
# Hourly: 0 * * * * cd /path/to/project && python -m app.tasks.billing_tasks hourly  
# Weekly on Sunday at 3 AM: 0 3 * * 0 cd /path/to/project && python -m app.tasks.billing_tasks weekly
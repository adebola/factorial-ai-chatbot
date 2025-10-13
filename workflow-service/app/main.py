from contextlib import asynccontextmanager
import asyncio
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from .core.config import settings
from .core.logging_config import setup_logging, get_logger
from .api import workflows, executions, triggers


async def periodic_cleanup():
    """
    Background task to periodically clean expired workflow states.
    Runs every hour (configurable via CLEANUP_INTERVAL_SECONDS env var).
    """
    from .core.database import SessionLocal
    from .services.state_manager import StateManager

    logger = get_logger("cleanup")

    # Get cleanup interval from environment (default: 1 hour)
    interval_seconds = int(os.environ.get("CLEANUP_INTERVAL_SECONDS", "3600"))

    while True:
        try:
            await asyncio.sleep(interval_seconds)

            db = SessionLocal()
            try:
                state_manager = StateManager(db)

                # Clean expired database states
                count = await state_manager.cleanup_expired_states()
                logger.info(f"Periodic cleanup removed {count} expired workflow states")

                # Clean orphaned Redis keys
                orphaned = await state_manager.cleanup_orphaned_redis_states()
                if orphaned > 0:
                    logger.info(f"Periodic cleanup removed {orphaned} orphaned Redis states")

            finally:
                db.close()

        except asyncio.CancelledError:
            logger.info("Cleanup task cancelled, shutting down")
            break
        except Exception as e:
            logger.error(f"Cleanup task failed: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger("main")
    logger.info("Starting Workflow Service", version="1.0.0")

    # Run initial cleanup on startup to remove stale data from previous runs
    from .core.database import SessionLocal
    from .services.state_manager import StateManager

    try:
        db = SessionLocal()
        try:
            state_manager = StateManager(db)
            count = await state_manager.cleanup_expired_states()
            if count > 0:
                logger.info(f"Startup cleanup removed {count} expired workflow states")

            orphaned = await state_manager.cleanup_orphaned_redis_states()
            if orphaned > 0:
                logger.info(f"Startup cleanup removed {orphaned} orphaned Redis states")

        finally:
            db.close()
    except Exception as e:
        logger.error(f"Startup cleanup failed: {e}", exc_info=True)

    # Start background cleanup task
    cleanup_task = asyncio.create_task(periodic_cleanup())
    logger.info("Background cleanup task started")

    yield

    # Cancel cleanup task on shutdown
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    logger.info("Shutting down Workflow Service")


def create_app() -> FastAPI:
    # Setup logging first
    setup_logging()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="Conversational workflow management and execution service",
        version="1.0.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
        lifespan=lifespan
    )

    # CORS is now handled by the Spring Cloud Gateway
    # No need for CORS middleware in the backend service

    # Include routers
    app.include_router(
        workflows.router,
        prefix=f"{settings.API_V1_STR}/workflows",
        tags=["workflows"]
    )

    app.include_router(
        executions.router,
        prefix=f"{settings.API_V1_STR}/executions",
        tags=["executions"]
    )

    app.include_router(
        triggers.router,
        prefix=f"{settings.API_V1_STR}/triggers",
        tags=["triggers"]
    )

    @app.get("/")
    async def root():
        return {
            "message": "Workflow Service",
            "version": "1.0.0",
            "status": "running",
            "docs_url": f"{settings.API_V1_STR}/docs"
        }

    @app.get("/health")
    async def health_check():
        return {
            "status": "healthy",
            "service": "workflow-service",
            "version": "1.0.0"
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True
    )
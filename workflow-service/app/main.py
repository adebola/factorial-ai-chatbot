from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from .core.config import settings
from .core.logging_config import setup_logging, get_logger
from .api import workflows, executions, triggers


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger("main")
    logger.info("Starting Workflow Service", version="1.0.0")

    yield

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
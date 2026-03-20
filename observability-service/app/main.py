import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from .core.config import settings
from .core.logging_config import setup_logging, get_logger
from .api import observe, sessions, backends, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger("main")
    logger.info("Starting Observability Service", version="1.0.0")

    yield

    logger.info("Shutting down Observability Service")


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="AI-powered observability agent for K8s/OpenTelemetry monitoring",
        version="1.0.0",
        openapi_url=f"{settings.API_V1_STR}/openapi.json",
        docs_url=f"{settings.API_V1_STR}/docs",
        redoc_url=f"{settings.API_V1_STR}/redoc",
        lifespan=lifespan,
        redirect_slashes=True
    )

    # Include routers
    app.include_router(
        observe.router,
        prefix=f"{settings.API_V1_STR}/observe",
        tags=["observe"]
    )

    app.include_router(
        sessions.router,
        prefix=f"{settings.API_V1_STR}/observe",
        tags=["sessions"]
    )

    app.include_router(
        backends.router,
        prefix=f"{settings.API_V1_STR}/observe",
        tags=["backends"]
    )

    app.include_router(
        health.router,
        tags=["health"]
    )

    @app.get("/")
    async def root():
        return {
            "message": "Observability Service",
            "version": "1.0.0",
            "status": "running",
            "docs_url": f"{settings.API_V1_STR}/docs"
        }

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8006,
        reload=True
    )

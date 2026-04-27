import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from .core.config import settings
from .core.logging_config import setup_logging, get_logger
from .core.telemetry import setup_telemetry
from .services.audit_publisher import audit_publisher
from .api import manifest, health, query, workspaces, documents


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger = get_logger("main")
    logger.info("Starting Legal Service", version="1.0.0")

    try:
        await audit_publisher.connect()
        logger.info("Audit publisher connected")
    except Exception as e:
        logger.warning(f"Audit publisher connection failed (non-critical): {e}")

    yield

    try:
        await audit_publisher.close()
    except Exception:
        pass

    logger.info("Shutting down Legal Service")


def create_app() -> FastAPI:
    setup_logging()

    app = FastAPI(
        title=settings.PROJECT_NAME,
        description="AI-powered legal intelligence for Nigerian legal practice",
        version="1.0.0",
        openapi_url=f"{settings.API_V1_STR}/legal/openapi.json",
        docs_url=f"{settings.API_V1_STR}/legal/docs",
        redoc_url=f"{settings.API_V1_STR}/legal/redoc",
        lifespan=lifespan,
        redirect_slashes=True,
    )

    setup_telemetry(app, service_name="legal-service")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routers
    app.include_router(
        workspaces.router,
        prefix=f"{settings.API_V1_STR}/legal",
        tags=["workspaces"],
    )

    app.include_router(
        documents.router,
        prefix=f"{settings.API_V1_STR}/legal",
        tags=["documents"],
    )

    app.include_router(
        query.router,
        prefix=f"{settings.API_V1_STR}/legal",
        tags=["query"],
    )

    app.include_router(health.router, tags=["health"])

    # Plugin manifest — unauthenticated, at root
    app.include_router(manifest.router, tags=["manifest"])

    # Request logging middleware
    logger = get_logger("main")

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        logger.info(
            "Request",
            method=request.method,
            path=request.url.path,
        )
        response = await call_next(request)
        logger.info(
            "Response",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
        return response

    @app.get("/")
    async def root():
        return {
            "message": "Legal Service",
            "version": "1.0.0",
            "status": "running",
            "docs_url": f"{settings.API_V1_STR}/legal/docs",
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8010, reload=True)

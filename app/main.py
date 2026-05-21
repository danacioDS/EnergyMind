import sys
from contextlib import asynccontextmanager
from pathlib import Path
from loguru import logger

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router
from app.services.query_service import QueryService


query_service: QueryService = None


def setup_logging():
    log_format = settings.log_format
    log_level = settings.log_level

    logger.remove()
    if log_format == "json":
        logger.add(
            sys.stdout,
            format="{time} | {level} | {message}",
            level=log_level,
            serialize=True,
        )
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | <cyan>{message}</cyan>",
            level=log_level,
            colorize=True,
        )

    log_file = Path("logs/lexenergy.log")
    log_file.parent.mkdir(exist_ok=True)
    logger.add(
        log_file,
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global query_service
    logger.info("Starting LexEnergy Bolivia...")
    setup_logging()
    query_service = QueryService()
    await query_service.initialize()
    logger.info("LexEnergy Bolivia ready")
    yield
    logger.info("Shutting down LexEnergy Bolivia...")
    if query_service:
        await query_service.close()
    logger.info("Shutdown complete")


app = FastAPI(
    title="LexEnergy Bolivia",
    description="Legal RAG Platform for Renewable Energy Investments in Bolivia",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        workers=settings.api_workers,
        reload=settings.api_debug,
    )

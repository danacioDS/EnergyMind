import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from loguru import logger

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import settings
from app.api.routes import router
from app.services.query_service import QueryService


query_service: QueryService = None


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())[:8]
        with logger.contextualize(correlation_id=cid):
            request.state.correlation_id = cid
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = cid
            return response


def setup_logging():
    log_format = settings.log_format
    log_level = settings.log_level

    logger.remove()
    logger.configure(extra={"correlation_id": "--------"})
    if log_format == "json":
        logger.add(
            sys.stdout,
            format="{time} | {level} | {extra[correlation_id]} | {message}",
            level=log_level,
            serialize=True,
        )
    else:
        logger.add(
            sys.stdout,
            format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | <cyan>{extra[correlation_id]: >8}</cyan> | {message}",
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
app.add_middleware(CorrelationIDMiddleware)

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

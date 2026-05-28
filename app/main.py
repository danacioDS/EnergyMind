import sys
import time
import uuid
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger

from app.config import settings
from app.api.routes import router
from core.runtime.resource_manager import ResourceManager


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        cid = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())[:8]

        with logger.contextualize(correlation_id=cid):
            request.state.correlation_id = cid

            response = await call_next(request)

            response.headers["X-Correlation-ID"] = cid
            return response


def setup_logging() -> None:
    log_format = settings.log_format
    log_level = settings.log_level

    logger.remove()

    logger.configure(
        extra={"correlation_id": "--------"}
    )

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
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level:8}</level> | "
                "<cyan>{extra[correlation_id]: >8}</cyan> | "
                "{message}"
            ),
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
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    t0 = time.perf_counter()
    logger.info("LexEnergy Bolivia starting (fast boot mode)...")

    rm = ResourceManager()
    app.state.resource_manager = rm
    app.state.ready = False
    app.state.query_service = None

    warmup_task = asyncio.create_task(
        _background_init(app, rm),
        name="lexenergy-warmup",
    )

    logger.info(f"API boot in {time.perf_counter() - t0:.3f}s — warmup running in background")

    yield

    warmup_task.cancel()
    try:
        await warmup_task
    except (asyncio.CancelledError, Exception):
        pass

    if app.state.query_service:
        await app.state.query_service.close()

    await rm.close()
    logger.info("Shutdown complete")


async def _background_init(app: FastAPI, rm: ResourceManager) -> None:
    try:
        t = time.perf_counter()

        await rm.warmup()

        from app.services.query_service import QueryService
        svc = QueryService(rm)
        await svc.initialize()
        app.state.query_service = svc
        app.state.ready = True

        logger.info(f"LexEnergy Bolivia fully ready in {time.perf_counter() - t:.2f}s")

    except Exception:
        logger.exception("Background init failed — service will return 503")
        app.state.ready = False


app = FastAPI(
    title="LexEnergy Bolivia",
    description="Legal RAG Platform for Renewable Energy Investments in Bolivia",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins.split(","),
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

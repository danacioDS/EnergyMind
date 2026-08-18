import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from loguru import logger
from app.api.routes import router
from app.config import settings
from app.middleware.correlation import CorrelationIDMiddleware
from app.utils.logging import setup_logging

_warmup_complete = False

def create_app() -> FastAPI:
    """Crea la aplicación FastAPI."""
    app = FastAPI(
        title="EnergyMind API",
        description="Legal RAG para legislación boliviana de energías renovables",
        version="0.1.0",
        lifespan=lifespan
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Correlation ID
    app.add_middleware(CorrelationIDMiddleware)
    
    # Router
    app.include_router(router)
    
    return app


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona el ciclo de vida de la aplicación."""
    setup_logging()
    logger.info("🚀 Starting EnergyMind...")
    
    from core.runtime.resource_manager import ResourceManager
    rm = ResourceManager()
    app.state.resource_manager = rm
    
    asyncio.create_task(_background_init(app, rm))
    
    yield
    
    logger.info("🛑 Shutting down...")
    await rm.cleanup()


async def _background_init(app: FastAPI, rm):
    global _warmup_complete
    
    try:
        logger.info("⏳ Warming up resources...")
        await asyncio.wait_for(rm.warmup(), timeout=60)
        
        _warmup_complete = True
        logger.info("✅ ResourceManager warmup complete")
        
        from app.services.query_service import QueryService
        
        # 🔥 CRÍTICO: Pasar rm a QueryService
        app.state.query_service = QueryService(rm)
        await app.state.query_service.initialize()
        logger.info("✅ QueryService initialized")
        
        app.state.ready = True
        logger.info("✅ App state set to ready")
        logger.info("🎉 EnergyMind is ready!")
        
    except asyncio.TimeoutError:
        logger.error("❌ Warmup timeout (60s)")
        app.state.ready = False
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        app.state.ready = False


app = create_app()

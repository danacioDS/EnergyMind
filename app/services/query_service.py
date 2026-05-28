import asyncio
import time
from typing import Optional, AsyncGenerator

from loguru import logger

from app.rag.pipeline import RAGPipeline
from app.agents.graph import LegalAgentGraph
from app.models.schemas import (
    QueryResponse,
    QueryRequest,
    RegulatoryAnalysis,
    LegalCitation,
    RiskMatrix,
    IncentiveInfo,
)
from app.services.sse_manager import SSEStreamManager
from app.services.cache import (
    init_redis,
    close_redis,
    get_cached,
    set_cached,
)
from app.config import settings


class QueryService:
    def __init__(self):
        self.pipeline: Optional[RAGPipeline] = None
        self.agent: Optional[LegalAgentGraph] = None
        self.redis_enabled = False

    async def initialize(self):
        logger.info("QS STEP 1 - starting QueryService.initialize()")

        total_timer = time.perf_counter()

        #
        # PIPELINE
        #
        try:
            logger.info("QS STEP 2 - creating RAGPipeline")

            t = time.perf_counter()

            self.pipeline = RAGPipeline()

            logger.info(
                f"QS STEP 3 - RAGPipeline created "
                f"({time.perf_counter() - t:.2f}s)"
            )

            logger.info("QS STEP 4 - initializing RAGPipeline")

            t = time.perf_counter()

            await asyncio.wait_for(
                self.pipeline.initialize(),
                timeout=180,
            )

            logger.info(
                f"QS STEP 5 - RAGPipeline initialized "
                f"({time.perf_counter() - t:.2f}s)"
            )

        except asyncio.TimeoutError:
            logger.exception(
                "RAGPipeline initialization timeout"
            )
            raise

        except Exception:
            logger.exception(
                "Failed initializing RAGPipeline"
            )
            raise

        #
        # AGENT
        #
        try:
            logger.info("QS STEP 6 - creating LegalAgentGraph")

            t = time.perf_counter()

            self.agent = LegalAgentGraph()

            logger.info(
                f"QS STEP 7 - LegalAgentGraph created "
                f"({time.perf_counter() - t:.2f}s)"
            )

            logger.info("QS STEP 8 - initializing LegalAgentGraph")

            t = time.perf_counter()

            await asyncio.wait_for(
                self.agent.initialize(),
                timeout=120,
            )

            logger.info(
                f"QS STEP 9 - LegalAgentGraph initialized "
                f"({time.perf_counter() - t:.2f}s)"
            )

        except asyncio.TimeoutError:
            logger.exception(
                "LegalAgentGraph initialization timeout"
            )
            raise

        except Exception:
            logger.exception(
                "Failed initializing LegalAgentGraph"
            )
            raise

        #
        # REDIS
        #
        logger.info("QS STEP 10 - initializing Redis")

        try:
            t = time.perf_counter()

            await asyncio.wait_for(
                init_redis(
                    host=settings.redis_host,
                    port=settings.redis_port,
                ),
                timeout=15,
            )

            self.redis_enabled = True

            logger.info(
                f"QS STEP 11 - Redis initialized "
                f"({time.perf_counter() - t:.2f}s)"
            )

        except asyncio.TimeoutError:
            logger.warning(
                "Redis initialization timeout — cache disabled"
            )

        except Exception:
            logger.exception(
                "Redis unavailable — cache disabled"
            )

        logger.info(
            f"QueryService initialized successfully "
            f"({time.perf_counter() - total_timer:.2f}s)"
        )

    async def close(self):
        logger.info("Closing QueryService")

        try:
            if self.pipeline:
                await self.pipeline.close()

        except Exception:
            logger.exception(
                "Error closing pipeline"
            )

        try:
            if self.redis_enabled:
                await close_redis()

        except Exception:
            logger.exception(
                "Error closing Redis"
            )

        logger.info("QueryService closed successfully")
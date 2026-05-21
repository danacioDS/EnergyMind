from typing import Optional
from loguru import logger

from app.rag.pipeline import RAGPipeline
from app.models.schemas import QueryResponse, QueryRequest


class QueryService:
    def __init__(self):
        self.pipeline: Optional[RAGPipeline] = None

    async def initialize(self):
        self.pipeline = RAGPipeline()
        await self.pipeline.initialize()
        logger.info("QueryService initialized")

    async def process_query(self, request: QueryRequest) -> QueryResponse:
        if not self.pipeline:
            raise RuntimeError("QueryService not initialized")

        response = await self.pipeline.query(
            question=request.question,
            subsector=request.subsector,
            tipo_norma=request.tipo_norma,
            vigente=request.vigente,
            top_k=request.top_k or 5,
        )

        logger.info(f"Query processed: {request.question[:60]}... -> {response.processing_time_ms}ms")
        return response

    async def close(self):
        if self.pipeline:
            await self.pipeline.close()

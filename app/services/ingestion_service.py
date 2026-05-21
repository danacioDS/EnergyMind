from loguru import logger
from ingestion.pipeline import IngestionPipeline


class IngestionService:
    def __init__(self):
        self.pipeline = IngestionPipeline()

    async def run_ingestion(self) -> int:
        logger.info("Starting ingestion service")
        count = await self.pipeline.run()
        logger.info(f"Ingestion service complete: {count} units")
        return count

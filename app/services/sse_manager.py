import json
from typing import AsyncGenerator, Dict, Any
from loguru import logger


class SSEStreamManager:
    def __init__(self, correlation_id: str = "--------"):
        self.correlation_id = correlation_id
    
    async def stream_generator(self, event_generator: AsyncGenerator[Dict[str, Any], None]) -> AsyncGenerator[str, None]:
        """Convierte un generador de eventos en un stream SSE"""
        try:
            async for event in event_generator:
                # Formatear evento SSE
                event_type = event.get("type", "message")
                event_data = json.dumps(event)
                
                yield f"event: {event_type}\n"
                yield f"data: {event_data}\n\n"
                
        except Exception as e:
            logger.error(f"SSE stream error: {e}")
            error_event = {
                "type": "error",
                "detail": str(e),
                "stage": "unknown"
            }
            yield f"event: error\n"
            yield f"data: {json.dumps(error_event)}\n\n"

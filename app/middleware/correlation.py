import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """Middleware que inyecta Correlation ID en cada request."""
    
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID")
        
        if not correlation_id:
            correlation_id = str(uuid.uuid4())
        
        # Inyectar en el estado de la request
        request.state.correlation_id = correlation_id
        
        # Inyectar en el contexto de loguru
        with logger.contextualize(correlation_id=correlation_id):
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
        
        return response

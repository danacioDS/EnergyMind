from loguru import logger
import sys
import os


def setup_logging():
    """Configura el logging con loguru."""
    # Remover handlers existentes
    logger.remove()
    
    # Console handler con colores
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level="INFO"
    )
    
    # File handler con correlation_id opcional
    if not os.path.exists("logs"):
        os.makedirs("logs", exist_ok=True)
    
    logger.add(
        "logs/app.log",
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {extra[correlation_id]:<36} | {name}:{function}:{line} - {message}",
        level="DEBUG"
    )
    
    # Inyectar correlation_id por defecto en el contexto
    logger.configure(extra={"correlation_id": "N/A"})
    
    logger.info("✅ Logging configured")

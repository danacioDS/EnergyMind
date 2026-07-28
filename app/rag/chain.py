from typing import Optional
from loguru import logger
from app.config import settings
from app.llm.router import LLMRouter


class LegalChain:
    def __init__(self) -> None:
        logger.info("🚀 INICIALIZANDO LEGALCHAIN CON LLM ROUTER")
        
        # Initialize router
        self.router = LLMRouter()
        
        logger.info("✅ LegalChain initialized with multi-provider fallback")
        logger.info(f"   Providers: {[p[0] for p in self.router.providers]}")

    def generate(self, prompt: str) -> str:
        """Genera una respuesta usando el router con fallback"""
        try:
            return self.router.generate(prompt)
        except Exception as e:
            logger.error(f"❌ All LLM providers failed: {e}")
            raise

    def _detect_language(self, text: str) -> str:
        import re
        spanish_patterns = r'[áéíóúñ¿¡]|el |la |los |las |de |que |en |por |con '
        english_patterns = r'the |to |of |and |for |with |on |at |from |by '
        portuguese_patterns = r'[áéíóúãõç]|o |a |os |as |de |que |em |por |com '
        
        text_lower = text.lower()
        spanish_score = len(re.findall(spanish_patterns, text_lower))
        english_score = len(re.findall(english_patterns, text_lower))
        portuguese_score = len(re.findall(portuguese_patterns, text_lower))
        
        if spanish_score >= english_score and spanish_score >= portuguese_score:
            return "spanish"
        elif portuguese_score > spanish_score and portuguese_score >= english_score:
            return "portuguese"
        return "english"

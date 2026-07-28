from typing import List, Tuple, Callable, Optional
from loguru import logger
from app.config import settings
from app.llm.providers import GroqLLM, GeminiLLM


class LLMRouter:
    """Router for multi-provider LLM fallback"""
    
    def __init__(self):
        self.providers = self._init_providers()
        self.failed_providers = []
        
        logger.info(f"LLM Router initialized with {len(self.providers)} providers")
        for i, (name, _) in enumerate(self.providers):
            logger.info(f"  {i+1}. {name}")
    
    def _init_providers(self) -> List[Tuple[str, Callable]]:
        providers = []
        
        # 1. Groq (Primary)
        if settings.groq_api_key:
            providers.append(("groq", lambda: GroqLLM(
                model=settings.groq_model or "llama-3.3-70b-versatile",
                api_key=settings.groq_api_key
            )))
        
        # 2. Gemini (Fallback)
        if settings.gemini_api_key:
            providers.append(("gemini", lambda: GeminiLLM(
                model=settings.gemini_model or "gemini-2.0-flash",
                api_key=settings.gemini_api_key
            )))
        
        if not providers:
            raise ValueError("No LLM providers configured. Check your API keys.")
        
        return providers
    
    def generate(self, prompt: str) -> str:
        """Generate response with automatic fallback"""
        
        for i, (name, provider_fn) in enumerate(self.providers):
            if name in self.failed_providers:
                continue
            
            try:
                logger.info(f"🔄 Trying provider: {name}")
                provider = provider_fn()
                response = provider.generate(prompt)
                logger.info(f"✅ Success with: {name}")
                
                # Reset failed providers on success
                self.failed_providers = []
                
                return response
                
            except Exception as e:
                logger.warning(f"❌ {name} failed: {e}")
                self.failed_providers.append(name)
                continue
        
        # All providers failed
        raise Exception("All LLM providers failed. Check your API keys and quotas.")
    
    def get_status(self) -> dict:
        """Get current status of all providers"""
        return {
            "total_providers": len(self.providers),
            "available_providers": [
                name for name, _ in self.providers 
                if name not in self.failed_providers
            ],
            "failed_providers": self.failed_providers
        }

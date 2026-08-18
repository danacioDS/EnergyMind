from typing import List, Tuple, Callable, Optional
from loguru import logger
from app.config import settings
from app.llm.providers import GroqLLM, CloudflareAI, GeminiLLM, OllamaProvider


class LLMRouter:
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
                model=settings.groq_model or "llama3-70b-8192",
                api_key=settings.groq_api_key
            )))
        
        # 2. Cloudflare Workers AI (Fallback)
        if settings.cloudflare_account_id and settings.cloudflare_api_token:
            providers.append(("cloudflare", lambda: CloudflareAI(
                account_id=settings.cloudflare_account_id,
                api_token=settings.cloudflare_api_token,
                model=settings.cloudflare_model or "@cf/meta/llama-3.1-8b-instruct"
            )))
        
        # 3. Gemini (Tercer fallback)
        if settings.gemini_api_key:
            providers.append(("gemini", lambda: GeminiLLM(
                model=settings.gemini_model or "gemini-2.5-flash",
                api_key=settings.gemini_api_key
            )))
        
        # 4. Ollama (Último fallback)
        providers.append(("ollama", lambda: OllamaProvider(
            base_url=settings.get("OLLAMA_BASE_URL", "http://localhost:11434"),
            model=settings.get("OLLAMA_MODEL", "llama3.2:1b")
        )))
        
        return providers
    
    def generate(self, prompt: str) -> str:
        for i, (name, provider_fn) in enumerate(self.providers):
            if name in self.failed_providers:
                continue
            
            try:
                logger.info(f"🔄 Trying provider: {name}")
                provider = provider_fn()
                response = provider.generate(prompt)
                
                if response is not None:
                    logger.info(f"✅ Provider {name} succeeded")
                    self.failed_providers = []
                    return response
                else:
                    logger.warning(f"❌ Provider {name} returned None")
                    self.failed_providers.append(name)
                    
            except Exception as e:
                logger.error(f"❌ Provider {name} failed: {e}")
                self.failed_providers.append(name)
        
        raise RuntimeError("All LLM providers failed. Check your API keys and quotas.")

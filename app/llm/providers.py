from typing import Optional
from loguru import logger
from app.config import settings


class GroqLLM:
    """LLM para Groq (Llama 3.3 70B)"""
    
    def __init__(self, model: str = "llama-3.3-70b-versatile", api_key: Optional[str] = None):
        self.model_name = model
        
        try:
            import groq
            self.client = groq.Groq(api_key=api_key)
            logger.info(f"✅ Groq client initialized with model: {model}")
        except ImportError:
            raise ImportError("Please install groq: pip install groq")
        except Exception as e:
            raise ValueError(f"Error initializing Groq: {e}")
    
    def generate(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=4096
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            raise


class GeminiLLM:
    """LLM para Google Gemini"""
    
    def __init__(self, model: str = "gemini-2.0-flash", api_key: Optional[str] = None):
        self.model_name = model
        
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self.client = genai.GenerativeModel(model)
            logger.info(f"✅ Gemini client initialized with model: {model}")
        except ImportError:
            raise ImportError("Please install google-generativeai: pip install google-generativeai")
        except Exception as e:
            raise ValueError(f"Error initializing Gemini: {e}")
    
    def generate(self, prompt: str) -> str:
        try:
            response = self.client.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise

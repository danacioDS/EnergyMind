import requests
import json
from typing import Optional
from loguru import logger


class GroqLLM:
    def __init__(self, api_key: str, model: str = "llama3-70b-8192"):
        self.api_key = api_key
        self.model = model
        self.failed = False
    
    def generate(self, prompt: str, **kwargs) -> Optional[str]:
        try:
            import groq
            client = groq.Groq(api_key=self.api_key)
            response = client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=kwargs.get("temperature", 0.1),
                max_tokens=kwargs.get("max_tokens", 2000),
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Groq API error: {e}")
            self.failed = True
            return None


class CloudflareAI:
    def __init__(self, account_id: str, api_token: str, model: str = "@cf/meta/llama-3.1-8b-instruct"):
        self.account_id = account_id
        self.api_token = api_token
        self.model = model
        self.failed = False
    
    def generate(self, prompt: str, **kwargs) -> Optional[str]:
        try:
            url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/run/{self.model}"
            
            headers = {
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": kwargs.get("temperature", 0.1),
                "max_tokens": kwargs.get("max_tokens", 2000),
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
            
            result = response.json()
            if result.get("success"):
                return result.get("result", {}).get("response", "")
            else:
                logger.error(f"Cloudflare API error: {result}")
                return None
                
        except Exception as e:
            logger.error(f"Cloudflare API error: {e}")
            self.failed = True
            return None


class GeminiLLM:
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        self.api_key = api_key
        self.model = model
        self.failed = False
    
    def generate(self, prompt: str, **kwargs) -> Optional[str]:
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            response = model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            self.failed = True
            return None


class OllamaProvider:
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3.2:1b"):
        self.base_url = base_url
        self.model = model
        self.failed = False
    
    def generate(self, prompt: str, **kwargs) -> Optional[str]:
        try:
            url = f"{self.base_url}/api/generate"
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": kwargs.get("temperature", 0.1),
                }
            }
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except Exception as e:
            logger.error(f"Ollama API error: {e}")
            self.failed = True
            return None

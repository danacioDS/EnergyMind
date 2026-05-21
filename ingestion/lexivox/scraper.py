import asyncio
from typing import List, Optional, Dict, Any
from pathlib import Path
from loguru import logger
import httpx
from bs4 import BeautifulSoup


LEXIVOX_BASE_URL = "https://www.lexivox.org"
LEXIVOX_SEARCH_URL = f"{LEXIVOX_BASE_URL}/search"


class LexivoxScraper:
    def __init__(self, base_url: str = LEXIVOX_BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "LexEnergy-Bolivia/1.0"},
        )

    async def search_norm(self, query: str, norm_type: Optional[str] = None) -> List[Dict[str, str]]:
        params: Dict[str, Any] = {"q": query}
        if norm_type:
            params["type"] = norm_type

        try:
            response = await self.client.get(LEXIVOX_SEARCH_URL, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            results: List[Dict[str, str]] = []
            for link in soup.select("a[href*='laws']"):
                href = link.get("href", "")
                title = link.get_text(strip=True)
                if title and href:
                    results.append({
                        "title": title,
                        "url": f"{self.base_url}{href}" if href.startswith("/") else href,
                    })
            return results
        except httpx.HTTPError as e:
            logger.error(f"Lexivox search failed: {e}")
            return []

    async def fetch_document(self, url: str) -> Optional[str]:
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            content_div = soup.select_one(".document-content, .law-content, #content, article")
            if content_div:
                return content_div.get_text(separator="\n", strip=True)
            return soup.get_text(separator="\n", strip=True)
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    async def fetch_norm_text(self, norm_id: str, norm_type: str = "Ley") -> Optional[str]:
        urls_to_try = [
            f"{self.base_url}/laws/{norm_id}",
            f"{self.base_url}/normas/{norm_id}",
            f"{self.base_url}/documento/{norm_id}",
        ]
        for url in urls_to_try:
            text = await self.fetch_document(url)
            if text and len(text) > 100:
                return text
        return None

    async def close(self):
        await self.client.aclose()

import asyncio
from typing import List, Optional, Dict, Any
from pathlib import Path
from loguru import logger
import httpx
from bs4 import BeautifulSoup


AETN_BASE_URL = "https://www.aetn.gob.bo"
AETN_RESOLUTIONS_URL = f"{AETN_BASE_URL}/resoluciones"


class AETNScraper:
    def __init__(self, base_url: str = AETN_BASE_URL):
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            verify_ssl=False,
            headers={"User-Agent": "LexEnergy-Bolivia/1.0"},
        )

    async def list_resolutions(self, year: Optional[int] = None, page: int = 1) -> List[Dict[str, str]]:
        params: Dict[str, Any] = {"page": page}
        if year:
            params["year"] = year

        try:
            response = await self.client.get(AETN_RESOLUTIONS_URL, params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            results: List[Dict[str, str]] = []
            for link in soup.select("a[href*='resolution'], a[href*='resolucion'], a[href*='RA']"):
                href = link.get("href", "")
                title = link.get_text(strip=True)
                if title and href:
                    results.append({
                        "title": title,
                        "url": f"{self.base_url}{href}" if href.startswith("/") else href,
                    })
            return results
        except httpx.HTTPError as e:
            logger.error(f"AETN list resolutions failed: {e}")
            return []

    async def fetch_resolution(self, url: str) -> Optional[str]:
        try:
            response = await self.client.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            content_div = soup.select_one(
                ".resolution-content, .document-content, #content, "
                ".entry-content, article, main"
            )
            if content_div:
                return content_div.get_text(separator="\n", strip=True)
            return soup.get_text(separator="\n", strip=True)
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch AETN resolution {url}: {e}")
            return None

    async def search_by_topic(self, topic: str) -> List[Dict[str, str]]:
        params = {"s": topic}
        try:
            response = await self.client.get(f"{self.base_url}/", params=params)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            results: List[Dict[str, str]] = []
            for link in soup.select("a[href*='resolucion'], a[href*='resolution'], a[href*='wp-content']"):
                href = link.get("href", "")
                title = link.get_text(strip=True)
                if title and href and len(title) > 5:
                    results.append({
                        "title": title,
                        "url": href if href.startswith("http") else f"{self.base_url}{href}",
                    })
            return results
        except httpx.HTTPError as e:
            logger.error(f"AETN search failed: {e}")
            return []

    async def close(self):
        await self.client.aclose()

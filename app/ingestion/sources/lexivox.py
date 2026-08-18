"""
Adaptador para LexiVox - URLs directas y scraping.
Soporta HTML, XHTML y diferentes formatos de artículos.
"""

import re
import httpx
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup
from loguru import logger
from app.ingestion.sources.base import LegalSourceAdapter


class LexiVoxAdapter(LegalSourceAdapter):
    """Adaptador para LexiVox usando URLs directas."""
    
    BASE_URL = "https://www.lexivox.org"
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)
    
    async def fetch(self, document_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Obtener un documento de LexiVox por su ID."""
        extensions = ['.html', '.xhtml']
        
        for ext in extensions:
            url = f"{self.BASE_URL}/norms/{document_id}{ext}"
            try:
                response = await self.client.get(url)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    doc = self._parse_document(soup, url)
                    if doc:
                        doc['id'] = document_id
                        logger.info(f"✅ LexiVox fetched: {document_id} ({ext})")
                        return doc
            except Exception:
                continue
        
        logger.error(f"❌ LexiVox fetch failed for {document_id}")
        return None
    
    async def search(self, query: str, **kwargs) -> List[Dict[str, Any]]:
        return []
    
    async def list_documents(self, **kwargs) -> List[Dict[str, Any]]:
        return []
    
    async def get_metadata(self, document_id: str) -> Dict[str, Any]:
        doc = await self.fetch(document_id)
        return doc.get('metadata', {}) if doc else {}
    
    def _parse_document(self, soup: BeautifulSoup, url: str) -> Optional[Dict[str, Any]]:
        try:
            content = soup.find('div', id='normTxtId')
            if not content:
                content = soup.find('div', class_='norma')
            if not content:
                content = soup.find('div', class_='contenido')
            if not content:
                content = soup.find('body')
            
            if not content:
                logger.warning("No se encontró el contenido de la norma")
                return None
            
            title_tag = content.find('h1')
            title_text = title_tag.text.strip() if title_tag else ""
            
            metadata = self._extract_metadata(soup)
            articles = self._extract_articles(content)
            
            # Si no hay artículos, usar todo el texto
            if not articles:
                text = content.text.strip()
                text = re.sub(r'\s+', ' ', text)
                articles = [{'numero': '1', 'texto': text}]
            
            full_text = self._build_full_text(articles)
            
            return {
                'title': title_text,
                'metadata': metadata,
                'articles': articles,
                'text': full_text,
                'url': url,
                'source': 'lexivox',
            }
            
        except Exception as e:
            logger.error(f"Failed to parse LexiVox document: {e}")
            return None
    
    def _extract_metadata(self, soup: BeautifulSoup) -> Dict[str, Any]:
        metadata = {}
        
        ficha = soup.find('table', class_='border1')
        if not ficha:
            ficha = soup.find('div', id='dcmi')
        
        if ficha:
            for row in ficha.find_all('tr'):
                cells = row.find_all(['th', 'td'])
                if len(cells) >= 2:
                    key = cells[0].text.strip().lower().replace(' ', '_')
                    value = cells[1].text.strip()
                    metadata[key] = value
        
        return metadata
    
    def _extract_articles(self, content: BeautifulSoup) -> List[Dict[str, Any]]:
        articles = []
        
        # 🔥 Patrones para diferentes formatos
        patterns = [
            # Artículo 1°.- (Alcance)
            r'Artículo\s+(\d+)[°º]?\.?\s*[-–—]?\s*(.*)',
            # Artículo Único.-
            r'Artículo\s+Único\.?\s*[-–—]?\s*(.*)',
            # Artículo 1.
            r'Artículo\s+(\d+)\.\s*(.*)',
        ]
        
        # Buscar en párrafos
        for p in content.find_all(['p', 'div']):
            text = p.text.strip()
            if not text:
                continue
            
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    if match.group(1).lower() == 'único':
                        articulo = 'Único'
                    else:
                        articulo = match.group(1)
                    texto = match.group(2).strip() if len(match.groups()) > 1 else ""
                    texto = re.sub(r'\s+', ' ', texto)
                    articles.append({
                        'numero': articulo,
                        'texto': f"Artículo {articulo}.- {texto}",
                    })
                    break
        
        # Si no hay, buscar en títulos
        if not articles:
            for tag in content.find_all(['h3', 'h4', 'h5']):
                text = tag.text.strip()
                for pattern in patterns:
                    match = re.search(pattern, text, re.IGNORECASE)
                    if match:
                        if match.group(1).lower() == 'único':
                            articulo = 'Único'
                        else:
                            articulo = match.group(1)
                        texto = match.group(2).strip() if len(match.groups()) > 1 else ""
                        articles.append({
                            'numero': articulo,
                            'texto': f"Artículo {articulo}.- {texto}",
                        })
                        break
        
        logger.info(f"📄 Extraídos {len(articles)} artículos")
        return articles
    
    def _build_full_text(self, articles: List[Dict[str, Any]]) -> str:
        return "\n\n".join([a.get('texto', '') for a in articles])
    
    async def close(self):
        await self.client.aclose()

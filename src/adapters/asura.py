import logging
from typing import List, Dict, Any, Optional
from src.adapters.base import BaseScraper
from src.normalizer import parse_chapter_info

logger = logging.getLogger(__name__)

class AsuraAdapter(BaseScraper):
    def __init__(self, base_url: str = "https://asuracomic.net", cf_cookie: Optional[str] = None, user_agent: Optional[str] = None, proxy_url: Optional[str] = None):
        super().__init__(site_code="ASURA", base_url=base_url, cf_cookie=cf_cookie, user_agent=user_agent, proxy_url=proxy_url)

    async def get_latest_chapters(self, relative_slug: str) -> List[Dict[str, Any]]:
        """
        Mengambil daftar chapter terbaru dari halaman series Asura.
        relative_slug contoh: '/series/solo-leveling' atau 'series/solo-leveling'
        Returns: [{'chapter_num': float, 'chapter_raw_title': str, 'chapter_url': str}]
        """
        html, new_base_url, status = await self.get_html(relative_slug)
        if not html:
            return []

        chapters: List[Dict[str, Any]] = []
        seen_urls = set()
        
        links = html.css("a[href*='/chapter/'], a[href*='-chapter-']")
        
        for a in links:
            href = a.attributes.get("href", "")
            title_text = a.text(strip=True)
            if not href or not title_text:
                continue

            full_url = href if href.startswith("http") else f"{self.base_url}/{href.lstrip('/')}"
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)
            
            ch_num, is_special, raw_title = parse_chapter_info(title_text)
            if ch_num is None:
                ch_num, is_special, _ = parse_chapter_info(href)

            if ch_num is not None:
                chapters.append({
                    "chapter_num": ch_num,
                    "chapter_raw_title": title_text,
                    "chapter_url": full_url,
                    "is_special": is_special
                })

        chapters.sort(key=lambda x: x["chapter_num"], reverse=True)
        return chapters

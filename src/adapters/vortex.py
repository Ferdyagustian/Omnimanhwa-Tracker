import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus, urlparse
from src.adapters.base import BaseScraper
from src.normalizer import parse_chapter_info

logger = logging.getLogger(__name__)

class VortexAdapter(BaseScraper):
    def __init__(self, base_url: str = "https://vortexscans.org", cf_cookie: Optional[str] = None, user_agent: Optional[str] = None, proxy_url: Optional[str] = None):
        super().__init__(site_code="VORTEX", base_url=base_url, cf_cookie=cf_cookie, user_agent=user_agent, proxy_url=proxy_url)

    async def search_comics(self, query: str) -> List[Dict[str, Any]]:
        """
        Mencari komik di VortexScans berdasarkan kata kunci judul.
        Returns: [{'slug': str, 'title': str, 'cover_url': Optional[str]}]
        """
        url = f"series?search={quote_plus(query)}"
        html, _, _ = await self.get_html(url)
        if not html:
            return []

        results: List[Dict[str, Any]] = []
        seen = set()
        for a in html.css("a[href*='/series/']"):
            href = a.attributes.get("href", "")
            if not href or any(x in href for x in ["/chapter", "/reader"]):
                continue
            text = a.text(strip=True) or a.attributes.get("title", "").strip()
            if not text or len(text) <= 2 or text.replace(".", "").isdigit():
                continue
            path = urlparse(href).path if href.startswith("http") else href
            clean_slug = path if path.startswith("/") else f"/{path}"
            if clean_slug in seen:
                continue
            seen.add(clean_slug)

            img = a.css_first("img")
            img_src = img.attributes.get("src") if img else None

            results.append({
                "slug": clean_slug,
                "title": text,
                "cover_url": img_src
            })
        return results

    async def get_latest_chapters(self, relative_slug: str) -> List[Dict[str, Any]]:
        html, new_base_url, status = await self.get_html(relative_slug)
        if not html:
            return []

        chapters: List[Dict[str, Any]] = []
        seen_urls = set()
        links = html.css("a[href*='chapter']")
        
        for a in links:
            href = a.attributes.get("href", "")
            title_text = a.text(strip=True)
            if not href or not title_text:
                continue

            full_url = href if href.startswith("http") else f"{self.base_url}/{href.lstrip('/')}"
            if full_url in seen_urls:
                continue
            seen_urls.add(full_url)

            ch_num_href, is_special_href, _ = parse_chapter_info(href)
            ch_num_text, is_special_text, _ = parse_chapter_info(title_text)

            ch_num = ch_num_href if ch_num_href is not None else ch_num_text
            is_special = is_special_href or is_special_text

            if ch_num is not None:
                chapters.append({
                    "chapter_num": ch_num,
                    "chapter_raw_title": f"Chapter {int(ch_num) if ch_num.is_integer() else ch_num}",
                    "chapter_url": full_url,
                    "is_special": is_special
                })

        chapters.sort(key=lambda x: x["chapter_num"], reverse=True)
        return chapters

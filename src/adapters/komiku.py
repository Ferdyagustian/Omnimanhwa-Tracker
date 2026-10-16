import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus, urlparse
from src.adapters.base import BaseScraper
from src.normalizer import parse_chapter_info

logger = logging.getLogger(__name__)

class KomikuAdapter(BaseScraper):
    def __init__(self, base_url: str = "https://komiku.org", cf_cookie: Optional[str] = None, user_agent: Optional[str] = None, proxy_url: Optional[str] = None):
        super().__init__(site_code="KOMIKU", base_url=base_url, cf_cookie=cf_cookie, user_agent=user_agent, proxy_url=proxy_url)

    async def search_comics(self, query: str) -> List[Dict[str, Any]]:
        """
        Mencari komik di Komiku berdasarkan kata kunci judul.
        Returns: [{'slug': str, 'title': str, 'cover_url': Optional[str]}]
        """
        # Gunakan API endpoint HTMX komiku untuk mendapatkan serial komik
        search_url = f"https://api.komiku.org/?post_type=manga&s={quote_plus(query)}"
        html, _, _ = await self.get_html(search_url)
        if not html:
            return []

        results: List[Dict[str, Any]] = []
        seen = set()
        for b in html.css(".bge"):
            a = b.css_first("a[href*='/manga/']") or b.css_first(".kan a") or b.css_first("a")
            if not a:
                continue
            href = a.attributes.get("href", "")
            if not href or "/manga/" not in href or any(x in href for x in ["/ch/", "/chapter", "genre", "category", "tag"]):
                continue

            h3 = b.css_first("h3")
            title = (h3.text(strip=True) if h3 else (a.text(strip=True) or a.attributes.get("title", ""))).strip()
            if not title or len(title) <= 2 or title.replace(".", "").isdigit():
                continue

            path = urlparse(href).path if href.startswith("http") else href
            clean_slug = path if path.startswith("/") else f"/{path}"
            if clean_slug in seen:
                continue
            seen.add(clean_slug)

            img = b.css_first("img")
            img_src = img.attributes.get("src") if img else None

            results.append({
                "slug": clean_slug,
                "title": title,
                "cover_url": img_src
            })
        return results

    async def get_latest_chapters(self, relative_slug: str) -> List[Dict[str, Any]]:
        """
        Mengambil daftar chapter terbaru dari halaman komik Komiku.
        relative_slug contoh: '/manga/solo-leveling'
        """
        html, new_base_url, status = await self.get_html(relative_slug)
        if not html:
            return []

        chapters: List[Dict[str, Any]] = []
        seen_urls = set()
        
        # Di Komiku: baris chapter berada di dalam tabel #Daftar_Chapter td.judulseries a
        links = html.css("#Daftar_Chapter a, .judulseries a, a[href*='/ch/'], a[href*='/chapter-']")
        
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

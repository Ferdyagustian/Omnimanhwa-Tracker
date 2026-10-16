import logging
from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus
from src.adapters.base import BaseScraper
from src.normalizer import parse_chapter_info

logger = logging.getLogger(__name__)

class AsuraAdapter(BaseScraper):
    def __init__(self, base_url: str = "https://asurascans.com", cf_cookie: Optional[str] = None, user_agent: Optional[str] = None, proxy_url: Optional[str] = None):
        super().__init__(site_code="ASURA", base_url=base_url, cf_cookie=cf_cookie, user_agent=user_agent, proxy_url=proxy_url)

    async def search_comics(self, query: str) -> List[Dict[str, Any]]:
        """
        Mencari komik di AsuraScans berdasarkan kata kunci judul.
        Returns: [{'slug': str, 'title': str, 'cover_url': Optional[str]}]
        """
        url = f"browse/comics?q={quote_plus(query)}"
        html, _, _ = await self.get_html(url)
        if not html:
            return []

        results: List[Dict[str, Any]] = []
        seen = set()
        for a in html.css("a[href*='/comics/']"):
            href = a.attributes.get("href", "")
            if not href or any(x in href for x in ["browse", "bookmarks", "chapter"]):
                continue
            text = a.text(strip=True)
            if not text or len(text) <= 2 or text.replace(".", "").isdigit():
                continue
            if href in seen:
                continue
            seen.add(href)
            
            # Cari gambar cover di dalam card jika ada
            img = a.css_first("img")
            img_src = img.attributes.get("src") if img else None
            
            results.append({
                "slug": href,
                "title": text,
                "cover_url": img_src
            })
        return results

    async def get_series_detail(self, relative_slug: str) -> Dict[str, Any]:
        """
        Mengambil detail series (judul, cover image, sinopsis)
        """
        html, _, _ = await self.get_html(relative_slug)
        if not html:
            return {}

        og_title = html.css_first("meta[property='og:title']")
        og_image = html.css_first("meta[property='og:image']")
        og_desc = html.css_first("meta[property='og:description']")

        title = og_title.attributes.get("content") if og_title else ""
        cover_url = og_image.attributes.get("content") if og_image else ""
        synopsis = og_desc.attributes.get("content") if og_desc else ""

        return {
            "title": title,
            "cover_url": cover_url,
            "synopsis": synopsis
        }

    async def get_latest_chapters(self, relative_slug: str) -> List[Dict[str, Any]]:
        """
        Mengambil daftar chapter terbaru dari halaman series Asura.
        relative_slug contoh: '/comics/shadow-slave-1bb35e56' atau 'comics/shadow-slave-1bb35e56'
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
            
            # Prioritaskan ekstrak nomor chapter dari URL href (/chapter/13) jika ada,
            # dan gabungkan deteksi is_special dari teks maupun href
            ch_num_href, is_special_href, _ = parse_chapter_info(href)
            ch_num_text, is_special_text, _ = parse_chapter_info(title_text)

            ch_num = ch_num_href if ch_num_href is not None else ch_num_text
            is_special = is_special_href or is_special_text

            if ch_num is not None:
                raw_title = f"Chapter {int(ch_num) if ch_num.is_integer() else ch_num}"
                chapters.append({
                    "chapter_num": ch_num,
                    "chapter_raw_title": raw_title,
                    "chapter_url": full_url,
                    "is_special": is_special
                })

        chapters.sort(key=lambda x: x["chapter_num"], reverse=True)
        return chapters

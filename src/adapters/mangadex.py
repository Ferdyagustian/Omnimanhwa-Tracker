import aiohttp
import logging
from typing import Optional, Dict, Any, List
from src.normalizer import normalize_title, parse_chapter_info
from src.config import Config

logger = logging.getLogger(__name__)

MANGADEX_API_BASE = "https://api.mangadex.org"

class MangaDexAdapter:
    def __init__(self, base_url: str = "https://mangadex.org", proxy_url: Optional[str] = None, **kwargs):
        self.site_code = "MANGADEX"
        self.base_url = base_url.rstrip("/")
        self.proxy_url = proxy_url or Config.PROXY_URL or None

    @classmethod
    async def search_manga(cls, title: str, proxy_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Cari manhwa di MangaDex berdasarkan judul.
        Mengembalikan data terstruktur: {uuid, canonical_title, cover_url, aliases}
        """
        url = f"{MANGADEX_API_BASE}/manga"
        params = {
            "title": title,
            "limit": 5,
            "includes[]": ["cover_art"]
        }
        
        headers = {
            "User-Agent": "OmniManhwaTracker/1.2"
        }
        proxy = proxy_url or Config.PROXY_URL or None

        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(url, params=params, proxy=proxy, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        logger.error(f"MangaDex API error {response.status}: {await response.text()}")
                        return None
                    data = await response.json()
            except Exception as e:
                logger.error(f"Gagal menghubungi MangaDex API: {e}")
                return None

        results = data.get("data", [])
        if not results:
            return None

        manga = results[0]
        manga_id = manga.get("id")
        attr = manga.get("attributes", {})
        
        titles = attr.get("title", {})
        canonical_title = titles.get("en") or next(iter(titles.values()), title)
        
        aliases: List[Dict[str, str]] = []
        alt_titles = attr.get("altTitles", [])
        for item in alt_titles:
            for lang, alt_name in item.items():
                if alt_name and alt_name.strip():
                    aliases.append({
                        "alias_title": alt_name.strip(),
                        "normalized_title": normalize_title(alt_name),
                        "lang_code": lang
                    })
        
        aliases.append({
            "alias_title": canonical_title,
            "normalized_title": normalize_title(canonical_title),
            "lang_code": "canonical"
        })

        cover_filename = None
        for rel in manga.get("relationships", []):
            if rel.get("type") == "cover_art":
                cover_filename = rel.get("attributes", {}).get("fileName")
                break
        
        cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{cover_filename}.256.jpg" if cover_filename else None

        return {
            "uuid": manga_id,
            "canonical_title": canonical_title,
            "cover_url": cover_url,
            "aliases": aliases
        }

    async def get_latest_chapters(self, relative_slug_or_uuid: str) -> List[Dict[str, Any]]:
        """
        Mengambil chapter terbaru dari MangaDex feed API.
        relative_slug_or_uuid bisa berupa MangaDex UUID atau slug format '/title/{uuid}'
        """
        # Bersihkan UUID jika berupa path
        clean_uuid = relative_slug_or_uuid.strip("/").split("/")[-1]
        url = f"{MANGADEX_API_BASE}/manga/{clean_uuid}/feed"
        params = {
            "translatedLanguage[]": ["en", "id"],
            "order[chapter]": "desc",
            "limit": 10
        }
        headers = {"User-Agent": "OmniManhwaTracker/1.2"}

        chapters: List[Dict[str, Any]] = []
        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(url, params=params, proxy=self.proxy_url, timeout=aiohttp.ClientTimeout(total=15)) as response:
                    if response.status != 200:
                        logger.warning(f"[MANGADEX] Feed API returned status {response.status}")
                        return []
                    data = await response.json()
            except Exception as e:
                logger.error(f"[MANGADEX] Gagal mengambil feed chapter {clean_uuid}: {e}")
                return []

        for item in data.get("data", []):
            chapter_id = item.get("id")
            attr = item.get("attributes", {})
            ch_str = attr.get("chapter")
            ch_title = attr.get("title") or f"Chapter {ch_str}"
            lang = (attr.get("translatedLanguage") or "en").upper()
            
            if not ch_str:
                continue

            try:
                ch_num = float(ch_str)
            except ValueError:
                continue

            chapters.append({
                "chapter_num": ch_num,
                "chapter_raw_title": ch_title,
                "chapter_url": f"https://mangadex.org/chapter/{chapter_id}",
                "is_special": False,
                "language": lang
            })

        chapters.sort(key=lambda x: x["chapter_num"], reverse=True)
        return chapters

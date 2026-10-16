import aiohttp
import logging
from typing import Optional, Dict, Any, List
from src.normalizer import normalize_title

logger = logging.getLogger(__name__)

MANGADEX_API_BASE = "https://api.mangadex.org"

class MangaDexAdapter:
    @staticmethod
    async def search_manga(title: str) -> Optional[Dict[str, Any]]:
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

        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as response:
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

        # Ambil hasil pertama paling relevan
        manga = results[0]
        manga_id = manga.get("id")
        attr = manga.get("attributes", {})
        
        # Ambil canonical title (prioritas 'en', lalu bahasa apapun yang ada)
        titles = attr.get("title", {})
        canonical_title = titles.get("en") or next(iter(titles.values()), title)
        
        # Kumpulkan semua altTitles
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
        
        # Tambahkan canonical title ke list alias juga jika belum ada
        aliases.append({
            "alias_title": canonical_title,
            "normalized_title": normalize_title(canonical_title),
            "lang_code": "canonical"
        })

        # Cari cover image dari relationships
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

import asyncio
import random
import logging
from typing import Optional, Tuple
from curl_cffi.requests import AsyncSession
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from src.db import Database

logger = logging.getLogger(__name__)

class BaseScraper:
    def __init__(self, site_code: str, base_url: str, cf_cookie: Optional[str] = None, user_agent: Optional[str] = None, proxy_url: Optional[str] = None):
        self.site_code = site_code
        self.base_url = base_url.rstrip("/")
        self.cf_cookie = cf_cookie
        self.user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        self.proxy_url = proxy_url

    async def get_html(self, path_or_url: str) -> Tuple[Optional[HTMLParser], Optional[str], int]:
        """
        Request halaman dengan curl_cffi TLS Chrome impersonation.
        Returns: (HTMLParser instance or None, new_base_url_if_redirected, http_status_code)
        """
        url = path_or_url if path_or_url.startswith("http") else f"{self.base_url}/{path_or_url.lstrip('/')}"
        
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        }
        
        cookies = {}
        if self.cf_cookie:
            cookies["cf_clearance"] = self.cf_cookie

        # Random jitter etika scraping (1 s.d. 2.5 detik)
        await asyncio.sleep(random.uniform(1.0, 2.5))

        proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None

        try:
            async with AsyncSession(impersonate="chrome124", proxies=proxies, verify=False) as session:
                response = await session.get(
                    url,
                    headers=headers,
                    cookies=cookies,
                    allow_redirects=True,
                    timeout=20
                )
                
                # Deteksi jika ada domain redirect (PRD FR-06 Auto-Healing)
                new_base_url = None
                if response.url and not response.url.startswith(self.base_url):
                    from urllib.parse import urlparse
                    parsed = urlparse(response.url)
                    new_base_url = f"{parsed.scheme}://{parsed.netloc}"
                    if new_base_url != self.base_url:
                        logger.info(f"[{self.site_code}] Auto-healing domain redirect: {self.base_url} -> {new_base_url}")
                        try:
                            await Database.update_site_base_url(self.site_code, new_base_url)
                            self.base_url = new_base_url
                        except Exception as dbe:
                            logger.warning(f"[{self.site_code}] Gagal persist redirect URL ke DB: {dbe}")

                if response.status_code == 200:
                    return HTMLParser(response.text), new_base_url, 200
                elif response.status_code in (403, 503):
                    logger.warning(f"[{self.site_code}] Terdeteksi proteksi WAF / Cloudflare (Status {response.status_code}) pada {url}")
                    return None, new_base_url, response.status_code
                else:
                    logger.warning(f"[{self.site_code}] HTTP error {response.status_code} pada {url}")
                    return None, new_base_url, response.status_code

        except Exception as e:
            logger.error(f"[{self.site_code}] Gagal mengambil halaman {url}: {e}")
            return None, None, 0

import uuid
import asyncpg
import logging
from typing import Optional, List, Dict, Any
from src.config import Config

logger = logging.getLogger(__name__)

class Database:
    _pool: Optional[asyncpg.Pool] = None

    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        if cls._pool is None:
            cls._pool = await asyncpg.create_pool(
                dsn=Config.get_db_dsn(),
                min_size=1,
                max_size=10,
                command_timeout=30
            )
            logger.info("Database connection pool initialized.")
        return cls._pool

    @classmethod
    async def close(cls):
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("Database connection pool closed.")

    @classmethod
    async def get_site_configs(cls) -> List[Dict[str, Any]]:
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM site_configs WHERE is_active = TRUE")
            return [dict(r) for r in rows]

    @classmethod
    async def update_site_base_url(cls, site_code: str, new_base_url: str):
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE site_configs SET base_url = $1 WHERE site_code = $2",
                new_base_url, site_code
            )
            logger.info(f"Updated base_url for {site_code} to {new_base_url}")

    @classmethod
    async def update_site_cf_cookie(cls, site_code: str, cookie: str, user_agent: str, expires_at):
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE site_configs 
                SET cf_clearance_cookie = $1, cf_user_agent = $2, cf_cookie_expires_at = $3, consecutive_failures = 0
                WHERE site_code = $4
                """,
                cookie, user_agent, expires_at, site_code
            )

    @classmethod
    async def insert_manhwa(cls, mangadex_uuid: Optional[str], canonical_title: str, cover_image_url: Optional[str]) -> int:
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            if mangadex_uuid:
                try:
                    uuid_obj = uuid.UUID(str(mangadex_uuid))
                except (ValueError, TypeError, AttributeError):
                    uuid_obj = None

                if uuid_obj:
                    row = await conn.fetchrow(
                        """
                        INSERT INTO manhwas (mangadex_uuid, canonical_title, cover_image_url)
                        VALUES ($1, $2, $3)
                        ON CONFLICT (mangadex_uuid) DO UPDATE 
                        SET canonical_title = EXCLUDED.canonical_title, cover_image_url = EXCLUDED.cover_image_url, updated_at = NOW()
                        RETURNING id
                        """,
                        uuid_obj, canonical_title, cover_image_url
                    )
                    return row["id"]

            row = await conn.fetchrow(
                """
                INSERT INTO manhwas (canonical_title, cover_image_url)
                VALUES ($1, $2)
                RETURNING id
                """,
                canonical_title, cover_image_url
            )
            return row["id"]

    @classmethod
    async def insert_alias(cls, manhwa_id: int, alias_title: str, normalized_title: str, lang_code: Optional[str]):
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO manhwa_aliases (manhwa_id, alias_title, normalized_title, lang_code)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (manhwa_id, normalized_title) DO NOTHING
                """,
                manhwa_id, alias_title, normalized_title, lang_code
            )

    @classmethod
    async def get_tracked_manhwas(cls) -> List[Dict[str, Any]]:
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM manhwas WHERE is_tracking = TRUE ORDER BY canonical_title ASC")
            return [dict(r) for r in rows]

    @classmethod
    async def get_tracked_manhwas_with_sources(cls) -> List[Dict[str, Any]]:
        """
        Mengambil daftar manhwa yang sedang dipantau beserta array sumber situs yang terikat.
        """
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT m.id, m.canonical_title, m.cover_image_url, 
                       m.latest_chapter_en, m.latest_chapter_id, m.created_at,
                       COALESCE(array_agg(s.site_code) FILTER (WHERE s.site_code IS NOT NULL), '{}') AS sources
                FROM manhwas m
                LEFT JOIN manhwa_sources s ON m.id = s.manhwa_id
                WHERE m.is_tracking = TRUE
                GROUP BY m.id
                ORDER BY m.canonical_title ASC
                """
            )
            return [dict(r) for r in rows]

    @classmethod
    async def get_manhwa_by_id(cls, manhwa_id: int) -> Optional[Dict[str, Any]]:
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM manhwas WHERE id = $1", manhwa_id)
            return dict(row) if row else None

    @classmethod
    async def delete_manhwa(cls, manhwa_id: int) -> Optional[str]:
        """
        Menghapus manhwa dari pantauan berdasarkan ID (cascade menghapus aliases, sources, dan logs).
        Mengembalikan judul kanonikal manhwa yang dihapus atau None jika tidak ditemukan.
        """
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "DELETE FROM manhwas WHERE id = $1 RETURNING canonical_title",
                manhwa_id
            )
            return row["canonical_title"] if row else None

    @classmethod
    async def get_aliases_for_manhwa(cls, manhwa_id: int) -> List[str]:
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT alias_title FROM manhwa_aliases WHERE manhwa_id = $1", manhwa_id)
            return [r["alias_title"] for r in rows]

    @classmethod
    async def bind_source(cls, manhwa_id: int, site_code: str, relative_slug: str):
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO manhwa_sources (manhwa_id, site_code, relative_slug, last_checked_at)
                VALUES ($1, $2, $3, NOW())
                ON CONFLICT (manhwa_id, site_code) DO UPDATE
                SET relative_slug = EXCLUDED.relative_slug, last_checked_at = NOW()
                """,
                manhwa_id, site_code, relative_slug
            )

    @classmethod
    async def record_chapter_log(cls, manhwa_id: int, site_code: str, language: str, chapter_num: float, chapter_raw_title: str, chapter_url: str) -> bool:
        """
        Mencatat chapter rilis. Mengembalikan True jika berhasil (belum pernah dinotifikasi),
        atau False jika URL chapter tersebut sudah ada (duplicate).
        """
        pool = await cls.get_pool()
        async with pool.acquire() as conn:
            try:
                await conn.execute(
                    """
                    INSERT INTO chapter_logs (manhwa_id, site_code, language, chapter_num, chapter_raw_title, chapter_url)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    manhwa_id, site_code, language, chapter_num, chapter_raw_title, chapter_url
                )
                
                # Update latest chapter tracker di tabel manhwas jika nomor lebih tinggi
                if language.upper() == "EN":
                    await conn.execute(
                        "UPDATE manhwas SET latest_chapter_en = GREATEST(latest_chapter_en, $1), updated_at = NOW() WHERE id = $2",
                        chapter_num, manhwa_id
                    )
                elif language.upper() == "ID":
                    await conn.execute(
                        "UPDATE manhwas SET latest_chapter_id = GREATEST(latest_chapter_id, $1), updated_at = NOW() WHERE id = $2",
                        chapter_num, manhwa_id
                    )
                return True
            except asyncpg.UniqueViolationError:
                return False

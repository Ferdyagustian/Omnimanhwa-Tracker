import os
import uuid
import sqlite3
import logging
from typing import Optional, List, Dict, Any
from src.config import Config

logger = logging.getLogger(__name__)

SQLITE_DB_PATH = "omnimanhwa.db"

class Database:
    _engine: str = "postgres"
    _pool: Any = None

    @classmethod
    def _init_sqlite(cls):
        """Inisialisasi skema SQLite lokal untuk development/testing tanpa Docker"""
        conn = sqlite3.connect(SQLITE_DB_PATH)
        conn.execute("PRAGMA journal_mode=WAL;")
        cur = conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS site_configs (
            site_code TEXT PRIMARY KEY,
            base_url TEXT NOT NULL,
            language TEXT NOT NULL,
            poll_interval_minutes INT DEFAULT 15,
            is_active INT DEFAULT 1,
            consecutive_failures INT DEFAULT 0,
            last_polled_at TIMESTAMP,
            cf_clearance_cookie TEXT,
            cf_user_agent TEXT,
            cf_cookie_expires_at TIMESTAMP,
            proxy_url TEXT
        );

        INSERT OR IGNORE INTO site_configs (site_code, base_url, language, poll_interval_minutes)
        VALUES 
            ('MANGADEX', 'https://mangadex.org', 'MULTI', 15),
            ('ASURA', 'https://asurascans.com', 'EN', 10),
            ('VORTEX', 'https://vortexscans.org', 'EN', 10),
            ('MGEKO', 'https://www.mgeko.cc', 'EN', 15),
            ('KOMIKU', 'https://komiku.org', 'ID', 15);

        CREATE TABLE IF NOT EXISTS manhwas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mangadex_uuid TEXT UNIQUE,
            canonical_title TEXT NOT NULL,
            cover_image_url TEXT,
            latest_chapter_en REAL DEFAULT 0,
            latest_chapter_id REAL DEFAULT 0,
            is_tracking INT DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS manhwa_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manhwa_id INT,
            alias_title TEXT NOT NULL,
            normalized_title TEXT NOT NULL,
            lang_code TEXT,
            UNIQUE(manhwa_id, normalized_title)
        );

        CREATE TABLE IF NOT EXISTS manhwa_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manhwa_id INT,
            site_code TEXT,
            relative_slug TEXT NOT NULL,
            last_chapter_num REAL DEFAULT 0,
            last_chapter_url TEXT,
            last_checked_at TIMESTAMP,
            UNIQUE(manhwa_id, site_code)
        );

        CREATE TABLE IF NOT EXISTS chapter_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            manhwa_id INT,
            site_code TEXT,
            language TEXT NOT NULL,
            chapter_num REAL NOT NULL,
            chapter_raw_title TEXT,
            chapter_url TEXT NOT NULL,
            notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(manhwa_id, site_code, chapter_url)
        );
        """)
        conn.commit()
        conn.close()
        logger.info(f"SQLite database initialized at {SQLITE_DB_PATH}")

    @classmethod
    async def get_pool(cls):
        if cls._pool is not None:
            return cls._pool

        # Coba koneksi ke PostgreSQL
        try:
            import asyncpg
            cls._pool = await asyncpg.create_pool(
                dsn=Config.get_db_dsn(),
                min_size=1,
                max_size=10,
                command_timeout=5
            )
            cls._engine = "postgres"
            logger.info("Database connection pool initialized (PostgreSQL).")
            return cls._pool
        except Exception as e:
            logger.warning(f"PostgreSQL tidak dapat dihubungi ({e}). Menggunakan SQLite lokal ({SQLITE_DB_PATH}).")
            cls._engine = "sqlite"
            cls._init_sqlite()
            cls._pool = "sqlite"
            return cls._pool

    @classmethod
    async def close(cls):
        if cls._engine == "postgres" and cls._pool and cls._pool != "sqlite":
            await cls._pool.close()
            cls._pool = None
            logger.info("Database connection pool closed.")

    @classmethod
    async def get_site_configs(cls) -> List[Dict[str, Any]]:
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM site_configs WHERE is_active = 1").fetchall()
            res = [dict(r) for r in rows]
            conn.close()
            return res
        else:
            async with cls._pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM site_configs WHERE is_active = TRUE")
                return [dict(r) for r in rows]

    @classmethod
    async def update_site_base_url(cls, site_code: str, new_base_url: str):
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.execute("UPDATE site_configs SET base_url = ? WHERE site_code = ?", (new_base_url, site_code))
            conn.commit()
            conn.close()
        else:
            async with cls._pool.acquire() as conn:
                await conn.execute("UPDATE site_configs SET base_url = $1 WHERE site_code = $2", new_base_url, site_code)
        logger.info(f"Updated base_url for {site_code} to {new_base_url}")

    @classmethod
    async def update_site_cf_cookie(cls, site_code: str, cookie: str, user_agent: str, expires_at):
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.execute(
                "UPDATE site_configs SET cf_clearance_cookie = ?, cf_user_agent = ?, cf_cookie_expires_at = ?, consecutive_failures = 0 WHERE site_code = ?",
                (cookie, user_agent, str(expires_at), site_code)
            )
            conn.commit()
            conn.close()
        else:
            async with cls._pool.acquire() as conn:
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
        await cls.get_pool()
        uuid_str = str(mangadex_uuid) if mangadex_uuid else None

        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            cur = conn.cursor()
            if uuid_str:
                cur.execute(
                    """
                    INSERT INTO manhwas (mangadex_uuid, canonical_title, cover_image_url)
                    VALUES (?, ?, ?)
                    ON CONFLICT(mangadex_uuid) DO UPDATE 
                    SET canonical_title = excluded.canonical_title, cover_image_url = excluded.cover_image_url, updated_at = CURRENT_TIMESTAMP
                    """,
                    (uuid_str, canonical_title, cover_image_url)
                )
                if cur.lastrowid:
                    manhwa_id = cur.lastrowid
                else:
                    cur.execute("SELECT id FROM manhwas WHERE mangadex_uuid = ?", (uuid_str,))
                    manhwa_id = cur.fetchone()[0]
            else:
                cur.execute(
                    "INSERT INTO manhwas (canonical_title, cover_image_url) VALUES (?, ?)",
                    (canonical_title, cover_image_url)
                )
                manhwa_id = cur.lastrowid
            conn.commit()
            conn.close()
            return manhwa_id
        else:
            async with cls._pool.acquire() as conn:
                if uuid_str:
                    try:
                        uuid_obj = uuid.UUID(uuid_str)
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
                    "INSERT INTO manhwas (canonical_title, cover_image_url) VALUES ($1, $2) RETURNING id",
                    canonical_title, cover_image_url
                )
                return row["id"]

    @classmethod
    async def insert_alias(cls, manhwa_id: int, alias_title: str, normalized_title: str, lang_code: Optional[str]):
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.execute(
                "INSERT OR IGNORE INTO manhwa_aliases (manhwa_id, alias_title, normalized_title, lang_code) VALUES (?, ?, ?, ?)",
                (manhwa_id, alias_title, normalized_title, lang_code)
            )
            conn.commit()
            conn.close()
        else:
            async with cls._pool.acquire() as conn:
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
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM manhwas WHERE is_tracking = 1 ORDER BY canonical_title ASC").fetchall()
            res = [dict(r) for r in rows]
            conn.close()
            return res
        else:
            async with cls._pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM manhwas WHERE is_tracking = TRUE ORDER BY canonical_title ASC")
                return [dict(r) for r in rows]

    @classmethod
    async def get_tracked_manhwas_with_sources(cls) -> List[Dict[str, Any]]:
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT m.id, m.canonical_title, m.cover_image_url, 
                       m.latest_chapter_en, m.latest_chapter_id, m.created_at,
                       GROUP_CONCAT(s.site_code) AS sources_str
                FROM manhwas m
                LEFT JOIN manhwa_sources s ON m.id = s.manhwa_id
                WHERE m.is_tracking = 1
                GROUP BY m.id
                ORDER BY m.canonical_title ASC
                """
            ).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                s_str = item.pop("sources_str", "")
                item["sources"] = s_str.split(",") if s_str else []
                results.append(item)
            conn.close()
            return results
        else:
            async with cls._pool.acquire() as conn:
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
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM manhwas WHERE id = ?", (manhwa_id,)).fetchone()
            res = dict(row) if row else None
            conn.close()
            return res
        else:
            async with cls._pool.acquire() as conn:
                row = await conn.fetchrow("SELECT * FROM manhwas WHERE id = $1", manhwa_id)
                return dict(row) if row else None

    @classmethod
    async def delete_manhwa(cls, manhwa_id: int) -> Optional[str]:
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT canonical_title FROM manhwas WHERE id = ?", (manhwa_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                return None
            title = row[0]
            cur.execute("DELETE FROM manhwas WHERE id = ?", (manhwa_id,))
            cur.execute("DELETE FROM manhwa_aliases WHERE manhwa_id = ?", (manhwa_id,))
            cur.execute("DELETE FROM manhwa_sources WHERE manhwa_id = ?", (manhwa_id,))
            cur.execute("DELETE FROM chapter_logs WHERE manhwa_id = ?", (manhwa_id,))
            conn.commit()
            conn.close()
            return title
        else:
            async with cls._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "DELETE FROM manhwas WHERE id = $1 RETURNING canonical_title",
                    manhwa_id
                )
                return row["canonical_title"] if row else None

    @classmethod
    async def bind_source(cls, manhwa_id: int, site_code: str, relative_slug: str):
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.execute(
                """
                INSERT INTO manhwa_sources (manhwa_id, site_code, relative_slug, last_checked_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(manhwa_id, site_code) DO UPDATE
                SET relative_slug = excluded.relative_slug, last_checked_at = CURRENT_TIMESTAMP
                """,
                (manhwa_id, site_code, relative_slug)
            )
            conn.commit()
            conn.close()
        else:
            async with cls._pool.acquire() as conn:
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
        await cls.get_pool()
        if cls._engine == "sqlite":
            conn = sqlite3.connect(SQLITE_DB_PATH)
            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO chapter_logs (manhwa_id, site_code, language, chapter_num, chapter_raw_title, chapter_url)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (manhwa_id, site_code, language, chapter_num, chapter_raw_title, chapter_url)
                )
                if language.upper() == "EN":
                    cur.execute(
                        "UPDATE manhwas SET latest_chapter_en = MAX(latest_chapter_en, ?), updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (chapter_num, manhwa_id)
                    )
                elif language.upper() == "ID":
                    cur.execute(
                        "UPDATE manhwas SET latest_chapter_id = MAX(latest_chapter_id, ?), updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (chapter_num, manhwa_id)
                    )
                conn.commit()
                conn.close()
                return True
            except sqlite3.IntegrityError:
                conn.close()
                return False
        else:
            async with cls._pool.acquire() as conn:
                try:
                    await conn.execute(
                        """
                        INSERT INTO chapter_logs (manhwa_id, site_code, language, chapter_num, chapter_raw_title, chapter_url)
                        VALUES ($1, $2, $3, $4, $5, $6)
                        """,
                        manhwa_id, site_code, language, chapter_num, chapter_raw_title, chapter_url
                    )
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
                except Exception:
                    return False

import asyncio
import logging
import signal
import random
from typing import Dict, Any
from src.config import Config
from src.db import Database
from src.bot.telegram_bot import setup_telegram_bot, send_release_notification
from src.adapters import ADAPTER_CLASSES, SITE_PRIORITY

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("OMTE_CORE")

async def poll_single_source(bot, manhwa: Dict[str, Any], source: Dict[str, Any], site_cfg: Dict[str, Any]):
    """
    Memeriksa satu sumber website untuk satu judul manhwa.
    """
    site_code = source["site_code"]
    adapter_cls = ADAPTER_CLASSES.get(site_code)
    if not adapter_cls:
        logger.warning(f"Adapter untuk {site_code} tidak ditemukan!")
        return

    adapter = adapter_cls(
        base_url=site_cfg.get("base_url", ""),
        cf_cookie=site_cfg.get("cf_clearance_cookie"),
        user_agent=site_cfg.get("cf_user_agent"),
        proxy_url=site_cfg.get("proxy_url")
    )

    slug = source["relative_slug"]
    logger.info(f"[{site_code}] Memeriksa manhwa '{manhwa['canonical_title']}' ({slug})...")
    
    chapters = await adapter.get_latest_chapters(slug)
    if not chapters:
        return

    default_lang = site_cfg.get("language", "EN")

    # Cek hingga 5 chapter terbaru dalam urutan nomor terkecil ke terbesar
    # untuk menangani jika ada rilis banyak chapter sekaligus (mass release)
    recent_chapters = list(reversed(chapters[:5]))
    for ch in recent_chapters:
        ch_num = ch["chapter_num"]
        raw_title = ch.get("chapter_raw_title", f"Chapter {ch_num}")
        ch_url = ch["chapter_url"]
        lang = ch.get("language") or default_lang
        is_special = ch.get("is_special", False)

        # Rekam ke database & cek apakah ini chapter baru (deduplikasi mutlak)
        is_new = await Database.record_chapter_log(
            manhwa_id=manhwa["id"],
            site_code=site_code,
            language=lang,
            chapter_num=ch_num,
            chapter_raw_title=raw_title,
            chapter_url=ch_url,
            is_special=is_special
        )

        if is_new and Config.TELEGRAM_ADMIN_CHAT_ID:
            logger.info(f"🎉 Chapter Baru Terdeteksi: '{manhwa['canonical_title']}' Ch. {ch_num} ({site_code} - {lang})! Mengirim notifikasi...")
            try:
                await send_release_notification(
                    bot=bot,
                    chat_id=Config.TELEGRAM_ADMIN_CHAT_ID,
                    title=manhwa["canonical_title"],
                    chapter_num=ch_num,
                    language=lang,
                    site_code=site_code,
                    chapter_url=ch_url,
                    cover_image_url=manhwa.get("cover_image_url")
                )
            except Exception as e:
                logger.error(f"Gagal mengirim notifikasi Telegram: {e}")

async def tracker_worker_loop(bot):
    """
    Background worker yang melakukan polling berkala ke semua manhwa yang terdaftar.
    """
    logger.info("Tracker background worker dimulai.")
    while True:
        try:
            site_configs_list = await Database.get_site_configs()
            site_map = {s["site_code"]: s for s in site_configs_list}

            manhwas = await Database.get_tracked_manhwas()
            for m in manhwas:
                sources = await Database.get_manhwa_sources(m["id"])
                # Urutkan sumber berdasarkan urutan prioritas: MGEKO -> MANGADEX -> VORTEX -> ASURA -> KOMIKU
                sources.sort(key=lambda s: SITE_PRIORITY.get(s["site_code"], 99))
                for s in sources:
                    site_cfg = site_map.get(s["site_code"])
                    if site_cfg and site_cfg.get("is_active", True):
                        await poll_single_source(bot, m, dict(s), site_cfg)
                        # Jitter antar request
                        await asyncio.sleep(random.uniform(1.5, 3.5))

            # Retensi Data berkala: bersihkan log notifikasi > 30 hari
            try:
                cleaned_count = await Database.cleanup_old_chapter_logs(days=30)
                if cleaned_count > 0:
                    logger.info(f"Retensi Data: Membersihkan {cleaned_count} log riwayat rilis lama (> 30 hari).")
            except Exception as ce:
                logger.warning(f"Gagal menjalankan retensi log: {ce}")

            # Jeda siklus polling berkala (default 20 menit) + Random Jitter (10 s.d. 35 detik)
            base_delay = Config.POLL_INTERVAL_MINUTES * 60
            jitter = random.uniform(10.0, 35.0)
            sleep_time = base_delay + jitter
            logger.info(f"Siklus selesai. Menunggu {int(sleep_time)} detik sebelum pengecekan berikutnya...")
            await asyncio.sleep(sleep_time)

        except asyncio.CancelledError:
            logger.info("Tracker worker dibatalkan.")
            break
        except Exception as e:
            logger.error(f"Error tidak terduga pada tracker worker: {e}", exc_info=True)
            await asyncio.sleep(30)

async def main():
    logger.info("Menginisialisasi OmniManhwa Tracker Engine (OMTE) v1.2...")
    
    # Init DB pool
    try:
        await Database.get_pool()
    except Exception as e:
        logger.warning(f"Database PostgreSQL belum terhubung ({e}). Jika berjalan di Docker, DB akan otomatis siap.")

    # Init Telegram Bot
    bot_app = setup_telegram_bot()
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()
    logger.info("Telegram Bot (@omnimanhwaBot) berhasil aktif & mendengarkan perintah.")

    # Jalankan background tracker
    tracker_task = asyncio.create_task(tracker_worker_loop(bot_app.bot))

    # Handle graceful shutdown
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    try:
        while not stop_event.is_set():
            await asyncio.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("Mematikan OMTE secara aman...")
        tracker_task.cancel()
        await bot_app.updater.stop()
        await bot_app.stop()
        await bot_app.shutdown()
        await Database.close()
        logger.info("OMTE berhasil dimatikan.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass

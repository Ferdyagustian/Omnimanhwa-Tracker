"""
Standalone Local Test Script (OMTE v1.2)
Menguji scraping live untuk:
1. Shadow Slave
2. The Necromancer of a Noble Sword Family (Sword of the Undying)
dan mengirimkan notifikasi rilis live ke bot Telegram pengguna.
"""

import asyncio
import logging
from telegram import Bot
from src.config import Config
from src.adapters.asura import AsuraAdapter
from src.bot.telegram_bot import send_release_notification

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("STANDALONE_TEST")

TARGETS = [
    {
        "title": "Shadow Slave",
        "slug": "/comics/shadow-slave-1bb35e56",
        "site_code": "ASURA",
        "language": "EN"
    },
    {
        "title": "The Necromancer of a Noble Sword Family",
        "slug": "/comics/sword-of-the-undying-1bb35e56",
        "site_code": "ASURA",
        "language": "EN"
    }
]

async def run_standalone_test():
    bot_token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_ADMIN_CHAT_ID

    if not bot_token or not chat_id:
        raise ValueError("TELEGRAM_BOT_TOKEN atau TELEGRAM_ADMIN_CHAT_ID belum diset di .env!")

    bot = Bot(token=bot_token)
    adapter = AsuraAdapter()

    logger.info(f"Memulai Standalone Test untuk {len(TARGETS)} judul manhwa...")
    results = []

    for target in TARGETS:
        title = target["title"]
        slug = target["slug"]
        site_code = target["site_code"]
        lang = target["language"]

        logger.info(f"--> [1/2] Melakukan scraping '{title}' dari {site_code} ({slug})...")
        
        # 1. Scraping Detail Series (Cover, dsb)
        detail = await adapter.get_series_detail(slug)
        cover_url = detail.get("cover_url")
        logger.info(f"    Cover Image URL: {cover_url}")

        # 2. Scraping Chapters
        chapters = await adapter.get_latest_chapters(slug)
        if not chapters:
            logger.error(f"    Gagal mengekstrak chapter untuk {title}!")
            continue

        latest_ch = chapters[0]
        ch_num = latest_ch["chapter_num"]
        ch_url = latest_ch["chapter_url"]
        logger.info(f"    Scraping Sukses! Total chapter: {len(chapters)} | Chapter Terbaru: Ch. {ch_num}")
        logger.info(f"    URL Chapter: {ch_url}")

        # 3. Kirim Notifikasi ke Telegram
        logger.info(f"--> [2/2] Mengirim notifikasi Telegram ke Chat ID {chat_id}...")
        try:
            await send_release_notification(
                bot=bot,
                chat_id=chat_id,
                title=title,
                chapter_num=ch_num,
                language=lang,
                site_code=site_code,
                chapter_url=ch_url,
                cover_image_url=cover_url
            )
            logger.info(f"    Notifikasi Telegram untuk '{title}' berhasil terkirim!")
            results.append({
                "title": title,
                "latest_chapter": ch_num,
                "chapter_url": ch_url,
                "telegram_sent": True
            })
        except Exception as e:
            logger.error(f"    Gagal mengirim notifikasi Telegram: {e}", exc_info=True)
            results.append({
                "title": title,
                "latest_chapter": ch_num,
                "chapter_url": ch_url,
                "telegram_sent": False,
                "error": str(e)
            })

        # Jeda 2 detik antar notifikasi
        await asyncio.sleep(2.0)

    print("\n" + "="*60)
    print("HASIL STANDALONE TEST SCRAPING & TELEGRAM:")
    print("="*60)
    all_success = True
    for r in results:
        status_sym = "[OK]" if r["telegram_sent"] else "[FAIL]"
        print(f"{status_sym} {r['title']}: Ch. {r['latest_chapter']} -> Telegram Sent: {r['telegram_sent']}")
        if not r["telegram_sent"]:
            all_success = False

    if all_success and len(results) == len(TARGETS):
        print("\n*** SEMUA WEBSITE BERHASIL DISCRAPE & NOTIFIKASI TELEGRAM BERHASIL TERKIRIM! ***")
    else:
        print("\n*** Ada kendala pada sebagian scraping atau notifikasi. ***")

if __name__ == "__main__":
    asyncio.run(run_standalone_test())

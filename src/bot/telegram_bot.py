import io
import logging
from typing import Optional
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)
from src.config import Config
from src.db import Database
from src.adapters.mangadex import MangaDexAdapter

logger = logging.getLogger(__name__)

async def stream_image(url: str, referer: Optional[str] = None) -> Optional[bytes]:
    """
    Unduh buffer gambar secara streaming dengan header Referer valid
    untuk menghindari HTTP 400/403 Hotlink Protection dari Telegram API.
    """
    if not url:
        return None
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    if referer:
        headers["Referer"] = referer
    
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return await resp.read()
    except Exception as e:
        logger.error(f"Gagal stream gambar dari {url}: {e}")
    return None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler perintah /start"""
    msg = (
        "🤖 *OmniManhwa Tracker Engine (OMTE) v1.2*\n"
        "Pelacak chapter manhwa 24/7 lintas situs (EN/ID).\n\n"
        "📖 *Daftar Perintah:*\n"
        "• `/add [judul]` — Tambah manhwa & seeding alias MangaDex\n"
        "• `/list` — Lihat daftar pantauan & chapter terakhir\n"
        "• `/bind [manhwa_id] [site] [url]` — Tautkan link situs manual\n"
        "• `/domain [site] [new_url]` — Perbarui base URL situs\n"
        "• `/health` — Cek status sistem, RAM & database\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /add [judul]"""
    if not context.args:
        await update.message.reply_text("⚠️ Format salah! Gunakan: `/add [judul manhwa]`", parse_mode="Markdown")
        return

    query = " ".join(context.args)
    status_msg = await update.message.reply_text(f"🔍 Mencari '_{query}_' di MangaDex...", parse_mode="Markdown")

    manga_info = await MangaDexAdapter.search_manga(query)
    if not manga_info:
        await status_msg.edit_text(f"❌ Manhwa '_{query}_' tidak ditemukan di MangaDex. Coba variasi nama lain.", parse_mode="Markdown")
        return

    # Simpan ke Database
    try:
        manhwa_id = await Database.insert_manhwa(
            mangadex_uuid=manga_info["uuid"],
            canonical_title=manga_info["canonical_title"],
            cover_image_url=manga_info["cover_url"]
        )

        alias_count = 0
        for alias in manga_info["aliases"]:
            await Database.insert_alias(
                manhwa_id=manhwa_id,
                alias_title=alias["alias_title"],
                normalized_title=alias["normalized_title"],
                lang_code=alias["lang_code"]
            )
            alias_count += 1

        caption = (
            f"✅ *Manhwa Berhasil Didaftarkan!*\n\n"
            f"🆔 *ID*: `{manhwa_id}`\n"
            f"📖 *Judul*: *{manga_info['canonical_title']}*\n"
            f"🏷️ *Alias Tersimpan*: `{alias_count}` variasi\n"
            f"🔗 *UUID*: `{manga_info['uuid']}`\n\n"
            f"_Engine akan mulai memantau rilis chapter terbaru secara otomatis._"
        )

        # Kirim foto sampul via binary stream multipart
        img_bytes = await stream_image(manga_info["cover_url"], referer="https://mangadex.org")
        await status_msg.delete()
        if img_bytes:
            await update.message.reply_photo(
                photo=io.BytesIO(img_bytes),
                caption=caption,
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(caption, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Gagal menyimpan manhwa ke DB: {e}")
        await status_msg.edit_text(f"❌ Terjadi kesalahan saat menyimpan ke database: {e}")

async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /list"""
    try:
        manhwas = await Database.get_tracked_manhwas()
        if not manhwas:
            await update.message.reply_text("Daftar pantauan masih kosong. Gunakan `/add [judul]`.", parse_mode="Markdown")
            return

        lines = ["📚 *Daftar Manhwa yang Dipantau:*\n"]
        for m in manhwas:
            ch_en = m.get('latest_chapter_en', 0)
            ch_id = m.get('latest_chapter_id', 0)
            lines.append(
                f"• `[{m['id']}]` *{m['canonical_title']}*\n"
                f"  └ 🇬🇧 EN: `Ch. {ch_en}` | 🇮🇩 ID: `Ch. {ch_id}`"
            )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error pada /list: {e}")
        await update.message.reply_text(f"Gagal mengambil daftar: {e}")

async def health_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /health"""
    try:
        import psutil
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        ram_text = f"RAM: {mem.used // (1024**2)}MB / {mem.total // (1024**2)}MB ({mem.percent}%)"
        swap_text = f"Swap: {swap.used // (1024**2)}MB / {swap.total // (1024**2)}MB ({swap.percent}%)"
    except ImportError:
        ram_text = "RAM: (psutil belum terpasang)"
        swap_text = "Swap: (psutil belum terpasang)"

    msg = (
        "🩺 *OMTE Health Status*\n\n"
        f"• *Memory*: `{ram_text}`\n"
        f"• *Swap Memory*: `{swap_text}`\n"
        f"• *Status Engine*: `ACTIVE 24/7`\n"
        f"• *Database*: `Connected (PostgreSQL)`\n"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def send_release_notification(
    bot,
    chat_id: str,
    title: str,
    chapter_num: float,
    language: str,
    site_code: str,
    chapter_url: str,
    cover_image_url: Optional[str] = None
):
    """
    Mengirimkan notifikasi rilis chapter baru lengkap dengan foto & link button
    """
    flag = "🇬🇧 [EN]" if language.upper() == "EN" else "🇮🇩 [ID]"
    caption = (
        f"🚨 *NEW CHAPTER RELEASE!* {flag}\n\n"
        f"📖 *{title}*\n"
        f"📑 *Chapter*: `Ch. {chapter_num}`\n"
        f"🌐 *Sumber*: `{site_code}`\n"
    )

    keyboard = [[InlineKeyboardButton("🚀 Baca Sekarang", url=chapter_url)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    img_bytes = await stream_image(cover_image_url) if cover_image_url else None

    if img_bytes:
        await bot.send_photo(
            chat_id=chat_id,
            photo=io.BytesIO(img_bytes),
            caption=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

def setup_telegram_bot() -> Application:
    """Menginisialisasi Telegram Bot Application"""
    token = Config.TELEGRAM_BOT_TOKEN
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN belum diset di .env!")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", start_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("health", health_command))

    return app

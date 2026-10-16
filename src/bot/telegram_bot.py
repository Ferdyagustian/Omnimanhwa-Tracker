import io
import logging
import asyncio
from typing import Optional
from urllib.parse import urlparse
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)
from src.config import Config
from src.db import Database
from src.adapters import ADAPTER_CLASSES, SITE_PRIORITY, MangaDexAdapter, AsuraAdapter
from src.resolver.matcher import EntityMatcher
from src.normalizer import normalize_title

logger = logging.getLogger(__name__)

VALID_SITES = ["MGEKO", "MANGADEX", "VORTEX", "ASURA", "KOMIKU"]

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
    """Handler perintah /start dan /help"""
    msg = (
        "🤖 *OmniManhwa Tracker Engine (OMTE) v1.2*\n"
        "Sistem Pelacak Chapter Manhwa 24/7 (EN/ID)\n\n"
        "📋 *Daftar Perintah Manajemen Target:*\n"
        "• `/add [judul atau URL]` — Tambahkan manhwa ke target pantauan\n"
        "• `/list` — Lihat semua manhwa yang sedang ditargetkan\n"
        "• `/delete [id]` — Hapus manhwa dari target pantauan (alias: `/remove`)\n"
        "• `/bind [manhwa_id] [situs] [slug/url]` — Tautkan link situs manual\n"
        "• `/domain [situs] [new_url]` — Perbarui base URL situs jika berganti\n"
        "• `/health` — Cek status server, RAM, Swap & database\n\n"
        "💡 *Contoh Cepat:*\n"
        "1. `/add Solo Leveling`\n"
        "2. `/add https://asurascans.com/comics/shadow-slave-1bb35e56`\n"
        "3. `/delete 1`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler /add [judul atau URL]
    Memindai keseluruhan website (MangaDex, Mgeko, AsuraScans, VortexScans, Komiku)
    dan mengaitkan seluruh website yang menyediakan judul tersebut secara otomatis.
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ Format salah!\nGunakan: `/add [judul atau URL]`\nContoh: `/add Solo Leveling` atau `/add https://asurascans.com/comics/shadow-slave-1bb35e56`",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args).strip()

    # Skenario 1: Input berupa URL langsung (misal dari AsuraScans)
    if query.startswith("http"):
        parsed = urlparse(query)
        path = parsed.path
        status_msg = await update.message.reply_text("🔍 Membaca detail manhwa dari URL langsung...", parse_mode="Markdown")

        asura = AsuraAdapter()
        detail = await asura.get_series_detail(path)
        title = detail.get("title") or path.strip("/").split("/")[-1].replace("-", " ").title()
        cover_url = detail.get("cover_url")

        manhwa_id = await Database.insert_manhwa(
            mangadex_uuid=None,
            canonical_title=title,
            cover_image_url=cover_url
        )
        await Database.insert_alias(
            manhwa_id=manhwa_id,
            alias_title=title,
            normalized_title=normalize_title(title),
            lang_code="en"
        )
        await Database.bind_source(manhwa_id=manhwa_id, site_code="ASURA", relative_slug=path)

        caption = (
            f"✅ *Target Manhwa Berhasil Ditambahkan via URL!*\n\n"
            f"🆔 *ID*: `{manhwa_id}`\n"
            f"📖 *Judul*: *{title}*\n"
            f"🌐 *Sumber Terikat*: `ASURA` (`{path}`)\n\n"
            f"_Engine akan otomatis memantau update chapter terbaru._"
        )

        img_bytes = await stream_image(cover_url, referer="https://asurascans.com") if cover_url else None
        await status_msg.delete()
        if img_bytes:
            await update.message.reply_photo(photo=io.BytesIO(img_bytes), caption=caption, parse_mode="Markdown")
        else:
            await update.message.reply_text(caption, parse_mode="Markdown")
        return

    # Skenario 2: Input berupa judul teks biasa (Memindai seluruh website)
    status_msg = await update.message.reply_text(f"🔍 Memindai keseluruhan website untuk '_{query}_'...", parse_mode="Markdown")

    bound_sites = []
    known_aliases = [query]
    canonical_title = query.title()
    cover_url = None
    manhwa_id = None

    # 2.1 Cek ke MangaDex terlebih dahulu untuk seeding data kanonikal & variasi alias
    manga_info = await MangaDexAdapter.search_manga(query)
    if manga_info:
        canonical_title = manga_info["canonical_title"]
        cover_url = manga_info.get("cover_url")
        manhwa_id = await Database.insert_manhwa(
            mangadex_uuid=manga_info["uuid"],
            canonical_title=canonical_title,
            cover_image_url=cover_url
        )

        for alias in manga_info["aliases"]:
            await Database.insert_alias(
                manhwa_id=manhwa_id,
                alias_title=alias["alias_title"],
                normalized_title=alias["normalized_title"],
                lang_code=alias["lang_code"]
            )
            known_aliases.append(alias["alias_title"])

        await Database.bind_source(
            manhwa_id=manhwa_id,
            site_code="MANGADEX",
            relative_slug=f"/title/{manga_info['uuid']}"
        )
        bound_sites.append("MANGADEX")
    else:
        manhwa_id = await Database.insert_manhwa(
            mangadex_uuid=None,
            canonical_title=canonical_title,
            cover_image_url=None
        )
        await Database.insert_alias(
            manhwa_id=manhwa_id,
            alias_title=query,
            normalized_title=normalize_title(query),
            lang_code="en"
        )

    # 2.2 Pindai seluruh website scanlator lainnya (Mgeko, Vortex, Asura, Komiku)
    site_configs = await Database.get_site_configs()
    site_map = {s["site_code"]: s for s in site_configs}

    async def scan_single_site(site_code: str):
        cfg = site_map.get(site_code, {})
        if not cfg.get("is_active", True):
            return None
        adapter_cls = ADAPTER_CLASSES.get(site_code)
        if not adapter_cls:
            return None
        adapter = adapter_cls(
            base_url=cfg.get("base_url", ""),
            cf_cookie=cfg.get("cf_clearance_cookie"),
            user_agent=cfg.get("cf_user_agent"),
            proxy_url=cfg.get("proxy_url")
        )
        try:
            results = await adapter.search_comics(canonical_title)
            if not results and query.lower() != canonical_title.lower():
                results = await adapter.search_comics(query)

            for r in results:
                is_match, score, _ = await EntityMatcher.match_candidate(
                    candidate_title=r["title"],
                    canonical_title=canonical_title,
                    known_aliases=known_aliases
                )
                if is_match or score >= 75.0:
                    return (site_code, r["slug"], r.get("cover_url"))
        except Exception as e:
            logger.warning(f"Gagal mencari di {site_code}: {e}")
        return None

    other_sites = ["MGEKO", "VORTEX", "ASURA", "KOMIKU"]
    scan_results = await asyncio.gather(*(scan_single_site(s) for s in other_sites), return_exceptions=True)

    for res in scan_results:
        if res and isinstance(res, tuple):
            s_code, s_slug, s_cover = res
            await Database.bind_source(manhwa_id=manhwa_id, site_code=s_code, relative_slug=s_slug)
            bound_sites.append(s_code)
            if not cover_url and s_cover:
                cover_url = s_cover

    if not bound_sites:
        await Database.delete_manhwa(manhwa_id)
        await status_msg.edit_text(
            f"❌ Manhwa '_{query}_' tidak ditemukan di website mana pun ({', '.join(VALID_SITES)}).\n\n"
            f"💡 Tips: Anda dapat menambahkan target menggunakan URL langsung, contoh:\n"
            f"`/add https://asurascans.com/comics/...`",
            parse_mode="Markdown"
        )
        return

    # Urutkan sumber yang terikat sesuai SITE_PRIORITY
    bound_sites.sort(key=lambda s: SITE_PRIORITY.get(s, 99))
    sites_str = ", ".join(f"`{s}`" for s in bound_sites)

    caption = (
        f"✅ *Target Manhwa Berhasil Didaftarkan!*\n\n"
        f"🆔 *ID*: `{manhwa_id}`\n"
        f"📖 *Judul*: *{canonical_title}*\n"
        f"🌐 *Sumber Terikat*: {sites_str}\n\n"
        f"_Engine otomatis membandingkan rilis chapter antar sumber dan memprioritaskan update tercepat._"
    )

    referer = "https://mangadex.org" if "MANGADEX" in bound_sites else "https://asurascans.com"
    img_bytes = await stream_image(cover_url, referer=referer) if cover_url else None
    await status_msg.delete()
    if img_bytes:
        await update.message.reply_photo(photo=io.BytesIO(img_bytes), caption=caption, parse_mode="Markdown")
    else:
        await update.message.reply_text(caption, parse_mode="Markdown")


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler /list
    Menampilkan semua manhwa yang sedang ditargetkan beserta sumber dan chapter terakhir.
    """
    try:
        manhwas = await Database.get_tracked_manhwas_with_sources()
        if not manhwas:
            await update.message.reply_text(
                "📭 *Daftar target pantauan masih kosong.*\n\n"
                "Gunakan `/add [judul atau URL]` untuk menambahkan manhwa baru ke daftar pantauan.",
                parse_mode="Markdown"
            )
            return

        lines = [f"📚 *Daftar Manhwa Target Pantauan (Total: {len(manhwas)}):*\n"]
        for idx, m in enumerate(manhwas, 1):
            ch_en = m.get('latest_chapter_en', 0)
            ch_id = m.get('latest_chapter_id', 0)
            sources_list = m.get('sources') or []
            sources_str = ", ".join(sources_list) if sources_list else "_Belum ada sumber terikat_"

            lines.append(
                f"{idx}. `[ID: {m['id']}]` *{m['canonical_title']}*\n"
                f"   ├ 🌐 Sumber: `{sources_str}`\n"
                f"   └ 🇬🇧 EN: `Ch. {ch_en}` | 🇮🇩 ID: `Ch. {ch_id}`\n"
            )

        lines.append(
            "💡 *Perintah Terkait:*\n"
            "• Hapus target: `/delete [id]` (contoh: `/delete 1`)\n"
            "• Tautkan link: `/bind [id] [situs] [url]`"
        )

        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error pada /list: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Gagal mengambil daftar target: {e}")

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler /delete [id] atau /remove [id]
    Menghapus manhwa target dari daftar pantauan.
    """
    if not context.args:
        await update.message.reply_text(
            "⚠️ Format salah!\nGunakan: `/delete [id]` atau `/remove [id]`\n"
            "Contoh: `/delete 1`\n\n"
            "💡 Ketik `/list` untuk melihat daftar nomor ID manhwa.",
            parse_mode="Markdown"
        )
        return

    try:
        manhwa_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ `ID` harus berupa angka bulat! Contoh: `/delete 1`", parse_mode="Markdown")
        return

    try:
        deleted_title = await Database.delete_manhwa(manhwa_id)
        if deleted_title:
            await update.message.reply_text(
                f"🗑️ *Manhwa Berhasil Dihapus!*\n\n"
                f"📖 Judul: *{deleted_title}*\n"
                f"🆔 ID: `{manhwa_id}`\n\n"
                f"_Manhwa beserta riwayat sumbernya tidak lagi dipantau oleh engine._",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ Manhwa dengan ID `{manhwa_id}` tidak ditemukan di daftar pantauan!\n"
                f"Ketik `/list` untuk memeriksa ID yang valid.",
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Error pada /delete: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Terjadi kesalahan saat menghapus manhwa: {e}")

async def bind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /bind [manhwa_id] [site_code] [slug_or_url]"""
    if not context.args or len(context.args) < 3:
        await update.message.reply_text(
            "⚠️ Format salah!\nGunakan: `/bind [manhwa_id] [site] [url_atau_slug]`\n"
            "Contoh: `/bind 1 ASURA /comics/shadow-slave-1bb35e56`\n"
            f"Situs valid: `{', '.join(VALID_SITES)}`",
            parse_mode="Markdown"
        )
        return

    try:
        manhwa_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ `manhwa_id` harus berupa angka bulat!", parse_mode="Markdown")
        return

    site_code = context.args[1].upper()
    if site_code not in VALID_SITES:
        await update.message.reply_text(
            f"❌ Situs `{site_code}` tidak valid! Pilihan: `{', '.join(VALID_SITES)}`",
            parse_mode="Markdown"
        )
        return

    raw_input_url = context.args[2]
    if raw_input_url.startswith("http"):
        parsed = urlparse(raw_input_url)
        relative_slug = parsed.path
    else:
        relative_slug = "/" + raw_input_url.lstrip("/")

    try:
        manhwa = await Database.get_manhwa_by_id(manhwa_id)
        if not manhwa:
            await update.message.reply_text(f"❌ Manhwa dengan ID `{manhwa_id}` tidak ditemukan!", parse_mode="Markdown")
            return

        await Database.bind_source(manhwa_id, site_code, relative_slug)
        await update.message.reply_text(
            f"✅ *Sumber Berhasil Ditautkan!*\n\n"
            f"📖 Manhwa: *{manhwa['canonical_title']}* (`ID: {manhwa_id}`)\n"
            f"🌐 Situs: `{site_code}`\n"
            f"🔗 Slug: `{relative_slug}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error pada /bind: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Gagal menautkan sumber: {e}")

async def domain_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler /domain [site_code] [new_base_url]"""
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ Format salah! Gunakan: `/domain [site] [new_base_url]`\n"
            "Contoh: `/domain ASURA https://asurascans.com`",
            parse_mode="Markdown"
        )
        return

    site_code = context.args[0].upper()
    if site_code not in VALID_SITES:
        await update.message.reply_text(
            f"❌ Situs `{site_code}` tidak valid! Pilihan: `{', '.join(sorted(VALID_SITES))}`",
            parse_mode="Markdown"
        )
        return

    new_base_url = context.args[1].rstrip("/")
    if not new_base_url.startswith("http"):
        await update.message.reply_text("❌ Base URL harus diawali dengan http:// atau https://", parse_mode="Markdown")
        return

    try:
        await Database.update_site_base_url(site_code, new_base_url)
        await update.message.reply_text(
            f"✅ *Base URL Diperbarui!*\n\n"
            f"🌐 Situs: `{site_code}`\n"
            f"🔗 New Base URL: `{new_base_url}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error pada /domain: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Gagal memperbarui domain: {e}")

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

    engine_name = getattr(Database, "_engine", "postgres").upper()
    msg = (
        "🩺 *OMTE Health Status*\n\n"
        f"• *Memory*: `{ram_text}`\n"
        f"• *Swap Memory*: `{swap_text}`\n"
        f"• *Status Engine*: `ACTIVE 24/7`\n"
        f"• *Database*: `Connected ({engine_name})`\n"
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
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("remove", delete_command))
    app.add_handler(CommandHandler("bind", bind_command))
    app.add_handler(CommandHandler("domain", domain_command))
    app.add_handler(CommandHandler("health", health_command))

    return app

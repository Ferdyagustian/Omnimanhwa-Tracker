import io
import logging
import asyncio
from functools import wraps
from typing import Optional
from urllib.parse import urlparse
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from src.config import Config
from src.db import Database
from src.adapters import ADAPTER_CLASSES, SITE_PRIORITY, MangaDexAdapter, AsuraAdapter
from src.resolver.matcher import EntityMatcher
from src.normalizer import normalize_title

logger = logging.getLogger(__name__)

VALID_SITES = ["MGEKO", "MANGADEX", "VORTEX", "ASURA", "KOMIKU"]

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📚 Daftar Pantauan", "➕ Tambah Komik"],
        ["🩺 Status Server", "❓ Panduan"]
    ],
    resize_keyboard=True
)

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

def is_authorized(update: Update) -> bool:
    """Memeriksa apakah pengirim perintah adalah admin yang sah"""
    if not Config.TELEGRAM_ADMIN_CHAT_ID:
        return True
    chat = update.effective_chat
    if not chat:
        return False
    return str(chat.id).strip() == str(Config.TELEGRAM_ADMIN_CHAT_ID).strip()

def admin_only(func):
    """Decorator pembatas hak akses hanya untuk admin"""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not is_authorized(update):
            if update.callback_query:
                await update.callback_query.answer("⛔ Akses ditolak: Anda bukan pengelola bot ini.", show_alert=True)
            elif update.message:
                await update.message.reply_text(
                    "⛔ *Akses Ditolak*\n────────────────────────\nAnda tidak memiliki izin untuk mengelola bot ini.",
                    parse_mode="Markdown"
                )
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler perintah /start dan /help dengan tata letak editorial Taste"""
    msg = (
        "⚡ *OmniManhwa Tracker Engine*\n"
        "────────────────────────\n"
        "Sistem Pelacak Chapter Manhwa 24/7 (EN/ID)\n\n"
        "📌 *Navigasi & Perintah:*\n"
        "• `/add [judul/URL]` — Tambah target pantauan\n"
        "• `/list [hal/judul]` — Lihat daftar komik & pencarian\n"
        "• `/check [id]` — Cek status rilis terakhir komik\n"
        "• `/delete [id]` — Hapus komik dari target\n"
        "• `/bind [id] [situs] [slug]` — Tautkan sumber manual\n"
        "• `/domain [situs] [url]` — Perbarui domain situs\n"
        "• `/health` — Metrik server & status engine\n\n"
        "💡 _Contoh:_ `/add Solo Leveling` atau `/list solo`"
    )
    await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)

@admin_only
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
        netloc = parsed.netloc.lower()
        path = parsed.path
        status_msg = await update.message.reply_text("🔍 Membaca detail manhwa dari URL langsung...", parse_mode="Markdown")

        # Tentukan website berdasarkan domain URL
        site_code = "ASURA"
        if "vortexscans" in netloc:
            site_code = "VORTEX"
        elif "mgeko" in netloc:
            site_code = "MGEKO"
        elif "komiku" in netloc:
            site_code = "KOMIKU"
        elif "mangadex" in netloc:
            site_code = "MANGADEX"

        # Normalisasi: jika URL mengarah ke chapter individual, potong menjadi URL serial
        series_path = path.split("/chapter")[0] if "/chapter" in path else path

        asura = AsuraAdapter()
        detail = await asura.get_series_detail(series_path) if site_code == "ASURA" else {}
        title = detail.get("title") or series_path.strip("/").split("/")[-1].replace("-", " ").title()
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
        await Database.bind_source(manhwa_id=manhwa_id, site_code=site_code, relative_slug=series_path)

        # Seeding awal chapter dari sumber URL ini secara senyap
        adapter_cls = ADAPTER_CLASSES.get(site_code)
        if adapter_cls:
            try:
                ad = adapter_cls()
                init_chs = await ad.get_latest_chapters(series_path)
                if init_chs:
                    lang = "ID" if site_code == "KOMIKU" else "EN"
                    for ch in init_chs[:5]:
                        await Database.record_chapter_log(
                            manhwa_id=manhwa_id,
                            site_code=site_code,
                            language=lang,
                            chapter_num=ch["chapter_num"],
                            chapter_raw_title=ch.get("chapter_raw_title", f"Chapter {ch['chapter_num']}"),
                            chapter_url=ch["chapter_url"],
                            is_special=ch.get("is_special", False)
                        )
            except Exception as se:
                logger.warning(f"Gagal seeding awal URL {site_code}: {se}")

        caption = (
            "✅ *TARGET DITAMBAHKAN (URL)*\n"
            "────────────────────────\n"
            f"📖 *{title}*\n"
            f"🆔 Target : `#{manhwa_id}`\n"
            f"🌐 Sumber : `{site_code}` (`{series_path}`)\n"
            "────────────────────────\n"
            "⚡ _Engine otomatis memantau rilis chapter 24/7._"
        )

        img_bytes = await stream_image(cover_url, referer="https://asurascans.com") if cover_url else None
        await status_msg.delete()
        if img_bytes:
            await update.message.reply_photo(photo=io.BytesIO(img_bytes), caption=caption, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
        else:
            await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
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
                if is_match:
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

    # Seeding awal status chapter secara senyap agar bot tidak spam notifikasi chapter lama
    for s_code in bound_sites:
        cfg = site_map.get(s_code, {})
        adapter_cls = ADAPTER_CLASSES.get(s_code)
        if not adapter_cls:
            continue
        try:
            sources = await Database.get_manhwa_sources(manhwa_id)
            source_map = {s["site_code"]: s["relative_slug"] for s in sources}
            s_slug = source_map.get(s_code)
            if s_slug:
                ad = adapter_cls(
                    base_url=cfg.get("base_url", ""),
                    cf_cookie=cfg.get("cf_clearance_cookie"),
                    user_agent=cfg.get("cf_user_agent"),
                    proxy_url=cfg.get("proxy_url")
                )
                init_chs = await ad.get_latest_chapters(s_slug)
                if init_chs:
                    lang = "ID" if s_code == "KOMIKU" else "EN"
                    for ch in init_chs[:5]:
                        await Database.record_chapter_log(
                            manhwa_id=manhwa_id,
                            site_code=s_code,
                            language=lang,
                            chapter_num=ch["chapter_num"],
                            chapter_raw_title=ch.get("chapter_raw_title", f"Chapter {ch['chapter_num']}"),
                            chapter_url=ch["chapter_url"],
                            is_special=ch.get("is_special", False)
                        )
        except Exception as se:
            logger.warning(f"Gagal seeding awal untuk {s_code}: {se}")

    # Urutkan sumber yang terikat sesuai SITE_PRIORITY
    bound_sites.sort(key=lambda s: SITE_PRIORITY.get(s, 99))
    sites_str = ", ".join(f"`{s}`" for s in bound_sites)

    caption = (
        "✅ *TARGET DITAMBAHKAN*\n"
        "────────────────────────\n"
        f"📖 *{canonical_title}*\n"
        f"🆔 Target : `#{manhwa_id}`\n"
        f"🌐 Sumber : {sites_str}\n"
        "────────────────────────\n"
        "⚡ _Engine otomatis membandingkan rilis tercepat 24/7._"
    )

    referer = "https://mangadex.org" if "MANGADEX" in bound_sites else "https://asurascans.com"
    img_bytes = await stream_image(cover_url, referer=referer) if cover_url else None
    await status_msg.delete()
    if img_bytes:
        await update.message.reply_photo(photo=io.BytesIO(img_bytes), caption=caption, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
    else:
        await update.message.reply_text(caption, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)


PAGE_SIZE = 5

def render_manhwa_list(manhwas: list, page: int = 1, filter_query: str = "") -> tuple[str, Optional[InlineKeyboardMarkup]]:
    """Merender tampilan daftar manhwa berhalaman (paginated) agar tidak melebihi batas 4096 karakter Telegram."""
    total = len(manhwas)
    if not total:
        if filter_query:
            return (
                f"🔍 *Tidak ditemukan manhwa dengan kata kunci:* `'{filter_query}'`\n\n"
                "Ketik `/list` untuk melihat semua target pantauan.",
                None
            )
        return (
            "📭 *Daftar target pantauan masih kosong.*\n\n"
            "Gunakan tombol *➕ Tambah Komik* atau ketik `/add [judul]` untuk mulai melacak.",
            None
        )

    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(1, min(page, total_pages))
    start_idx = (page - 1) * PAGE_SIZE
    page_items = manhwas[start_idx:start_idx + PAGE_SIZE]

    header = f"🔍 *HASIL PENCARIAN:* `'{filter_query}'`" if filter_query else "📚 *TARGET PANTAUAN*"
    lines = [
        f"{header} `({total} Judul │ Hal {page}/{total_pages})`",
        "────────────────────────"
    ]
    del_buttons = []
    for m in page_items:
        ch_en = m.get('latest_chapter_en', 0)
        ch_id = m.get('latest_chapter_id', 0)
        sources_list = m.get('sources') or []
        sources_str = " · ".join(sources_list) if sources_list else "Belum terikat"

        lines.append(
            f"#{m['id']} *{m['canonical_title']}*\n"
            f"├ 🌐 `{sources_str}`\n"
            f"└ 🇬🇧 `Ch. {ch_en}` │ 🇮🇩 `Ch. {ch_id}`\n"
        )
        del_buttons.append(InlineKeyboardButton(f"🗑️ #{m['id']}", callback_data=f"del_ask:{m['id']}"))

    lines.append("────────────────────────")
    lines.append("💡 _Ketuk tombol di bawah untuk menghapus target._")

    keyboard = [del_buttons[i:i+3] for i in range(0, len(del_buttons), 3)]

    if total_pages > 1:
        nav_row = []
        suffix = f":{filter_query[:20]}" if filter_query else ""
        if page > 1:
            nav_row.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"list_page:{page - 1}{suffix}"))
        nav_row.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="noop"))
        if page < total_pages:
            nav_row.append(InlineKeyboardButton("Selanjutnya ➡️", callback_data=f"list_page:{page + 1}{suffix}"))
        keyboard.append(nav_row)

    return "\n".join(lines), InlineKeyboardMarkup(keyboard) if keyboard else None

@admin_only
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler /list [halaman | keyword]
    Menampilkan semua manhwa yang sedang ditargetkan dengan pagination kartu editorial Taste & tombol aksi cepat.
    Mendukung lompat ke nomor halaman (/list 5) atau pencarian judul (/list solo).
    """
    try:
        manhwas = await Database.get_tracked_manhwas_with_sources()
        target_page = 1
        filter_query = ""

        if context.args:
            arg = " ".join(context.args).strip()
            if arg.isdigit():
                target_page = int(arg)
            else:
                filter_query = arg
                manhwas = [m for m in manhwas if filter_query.lower() in m["canonical_title"].lower()]

        text, reply_markup = render_manhwa_list(manhwas, page=target_page, filter_query=filter_query)
        if not manhwas and not filter_query:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_KEYBOARD)
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Error pada /list: {e}", exc_info=True)
        await update.message.reply_text(f"❌ Gagal mengambil daftar target: {e}")

@admin_only
async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handler /check [id]
    Mengecek kapan manhwa terakhir kali dirilis chapternya, pada tanggal berapa, 
    dan status sumber yang terikat.
    """
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "ℹ️ *Format salah!*\nGunakan: `/check [id_manhwa]`\nContoh: `/check 1`",
            parse_mode="Markdown"
        )
        return

    m_id = int(context.args[0])
    status_msg = await update.message.reply_text(f"🔍 *Mengecek status Manhwa #{m_id}...*", parse_mode="Markdown")

    try:
        manhwa = await Database.get_manhwa_by_id(m_id)
        if not manhwa:
            await status_msg.edit_text(f"❌ Manhwa dengan ID `#{m_id}` tidak ditemukan dalam daftar pantauan.", parse_mode="Markdown")
            return

        title = manhwa["canonical_title"]
        ch_en = manhwa.get("latest_chapter_en", 0)
        ch_id = manhwa.get("latest_chapter_id", 0)

        # Ambil data rilis terakhir dari database
        latest_rel = await Database.get_latest_release_info(m_id)

        # Ambil daftar sumber yang terikat
        sources = await Database.get_manhwa_sources(m_id)
        sources_str = ", ".join(f"`{s['site_code']}`" for s in sources) if sources else "Belum terikat"

        if latest_rel:
            rel_site = latest_rel.get("site_code", "-")
            rel_lang = latest_rel.get("language", "-")
            rel_num = latest_rel.get("chapter_num", "-")
            rel_title = latest_rel.get("chapter_raw_title", f"Chapter {rel_num}")
            rel_url = latest_rel.get("chapter_url", "")
            raw_time = latest_rel.get("notified_at")
            if hasattr(raw_time, "strftime"):
                date_str = raw_time.strftime("%d %b %Y, %H:%M WIB")
            elif raw_time:
                date_str = str(raw_time)[:16]
            else:
                date_str = "Baru saja"

            release_section = (
                f"🕒 *Rilis Terakhir Terdeteksi:*\n"
                f"├ *Chapter:* `{rel_title}` (`{rel_site}` - `{rel_lang}`)\n"
                f"├ *Tanggal:* `{date_str}`\n"
                f"└ *Tautan:* [Buka Chapter]({rel_url})\n"
            )
        else:
            release_section = "🕒 *Rilis Terakhir Terdeteksi:*\n└ _Belum ada log rilis chapter yang terekam._\n"

        response_text = (
            f"📖 *STATUS TARGET: {title}*\n"
            f"🆔 *ID Target:* `#{m_id}`\n"
            f"────────────────────────\n"
            f"🇬🇧 *Progres EN:* `Ch. {ch_en}`\n"
            f"🇮🇩 *Progres ID:* `Ch. {ch_id}`\n\n"
            f"{release_section}"
            f"────────────────────────\n"
            f"🌐 *Sumber Terikat:* {sources_str}\n"
            f"⚡ _Status: Siap dipantau 24/7._"
        )

        await status_msg.edit_text(response_text, parse_mode="Markdown", disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error pada /check: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ Terjadi kesalahan saat memeriksa target: {e}")

@admin_only
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

@admin_only
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

@admin_only
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

@admin_only
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
        "🩺 *STATUS SERVER & ENGINE*\n"
        "────────────────────────\n"
        f"• *Status Engine* : `ONLINE (24/7)`\n"
        f"• *RAM*           : `{ram_text}`\n"
        f"• *Swap*          : `{swap_text}`\n"
        f"• *Database*      : `{engine_name} Connected`\n"
        "────────────────────────\n"
        "🚀 _Semua adapter aktif & siap mendeteksi rilis._"
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
    Mengirimkan notifikasi rilis chapter baru dengan format kartu editorial Taste
    """
    flag = "🇬🇧 EN" if language.upper() == "EN" else "🇮🇩 ID"
    caption = (
        f"🚨 *NEW CHAPTER RELEASE* │ {flag}\n"
        "────────────────────────\n"
        f"📖 *{title}*\n"
        f"📑 Chapter : `Ch. {chapter_num}`\n"
        f"🌐 Sumber  : `{site_code}`\n"
        "────────────────────────\n"
        "⚡ _Update terdeteksi oleh OmniManhwa Engine._"
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

@admin_only
async def quick_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler pesan tombol navigasi cepat (Reply Keyboard)"""
    text = (update.message.text or "").strip()
    if text == "📚 Daftar Pantauan":
        await list_command(update, context)
    elif text == "➕ Tambah Komik":
        await update.message.reply_text(
            "➕ *Tambah Target Manhwa*\n"
            "────────────────────────\n"
            "Kirim pesan dengan format:\n"
            "`/add [judul komik]` atau `/add [link URL]`\n\n"
            "💡 _Contoh:_\n"
            "• `/add Solo Leveling`\n"
            "• `/add https://asurascans.com/comics/...`",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD
        )
    elif text == "🩺 Status Server":
        await health_command(update, context)
    elif text == "❓ Panduan":
        await start_command(update, context)

@admin_only
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler aksi inline button: konfirmasi hapus dua tahap"""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data.startswith("del_ask:"):
        try:
            m_id = int(data.split(":")[1])
            manhwa = await Database.get_manhwa_by_id(m_id)
            title = manhwa["canonical_title"] if manhwa else f"Target #{m_id}"
            confirm_kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Ya, Hapus", callback_data=f"del_yes:{m_id}"),
                    InlineKeyboardButton("❌ Batal", callback_data="del_cancel")
                ]
            ])
            await query.edit_message_text(
                f"⚠️ *Konfirmasi Hapus Target*\n"
                f"────────────────────────\n"
                f"Yakin ingin menghapus *{title}* (`#{m_id}`) dari daftar pantauan?",
                parse_mode="Markdown",
                reply_markup=confirm_kb
            )
        except Exception as e:
            logger.error(f"Error pada del_ask: {e}")
            await query.edit_message_text(f"❌ Terjadi kesalahan: {e}")

    elif data.startswith("list_page:"):
        try:
            parts = data.split(":")
            page = int(parts[1])
            filter_query = parts[2] if len(parts) > 2 else ""
            manhwas = await Database.get_tracked_manhwas_with_sources()
            if filter_query:
                manhwas = [m for m in manhwas if filter_query.lower() in m["canonical_title"].lower()]
            text, reply_markup = render_manhwa_list(manhwas, page=page, filter_query=filter_query)
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error on list_page: {e}")

    elif data == "noop":
        pass

    elif data.startswith("del_yes:"):
        try:
            m_id = int(data.split(":")[1])
            deleted_title = await Database.delete_manhwa(m_id)
            if deleted_title:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("📚 Kembali ke Daftar", callback_data="list_page:1")]])
                await query.edit_message_text(
                    f"🗑️ *Target Berhasil Dihapus*\n"
                    f"────────────────────────\n"
                    f"*{deleted_title}* (`#{m_id}`) tidak lagi dipantau oleh engine.",
                    parse_mode="Markdown",
                    reply_markup=kb
                )
            else:
                await query.edit_message_text(f"❌ Target `#{m_id}` tidak ditemukan.", parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Error pada del_yes: {e}")
            await query.edit_message_text(f"❌ Gagal menghapus target: {e}")

    elif data == "del_cancel":
        manhwas = await Database.get_tracked_manhwas_with_sources()
        text, reply_markup = render_manhwa_list(manhwas, page=1)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)

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
    app.add_handler(CommandHandler("check", check_command))
    app.add_handler(CommandHandler("delete", delete_command))
    app.add_handler(CommandHandler("remove", delete_command))
    app.add_handler(CommandHandler("bind", bind_command))
    app.add_handler(CommandHandler("domain", domain_command))
    app.add_handler(CommandHandler("health", health_command))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, quick_button_handler))

    return app

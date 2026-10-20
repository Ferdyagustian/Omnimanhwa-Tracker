import unittest
from urllib.parse import urlparse
from src.bot.telegram_bot import setup_telegram_bot, VALID_SITES

class TestTelegramBot(unittest.TestCase):
    def test_valid_sites_definition(self):
        expected = ["MGEKO", "MANGADEX", "VORTEX", "ASURA", "KOMIKU"]
        self.assertEqual(VALID_SITES, expected)

    def test_slug_normalization_logic(self):
        # Case 1: Full URL with domain
        full_url = "https://asuracomic.net/series/solo-leveling"
        parsed = urlparse(full_url)
        slug1 = parsed.path
        self.assertEqual(slug1, "/series/solo-leveling")

        # Case 2: Relative string without leading slash
        rel_str = "series/solo-leveling"
        slug2 = "/" + rel_str.lstrip("/")
        self.assertEqual(slug2, "/series/solo-leveling")

        # Case 3: Already with leading slash
        rel_slash = "/series/solo-leveling"
        slug3 = "/" + rel_slash.lstrip("/")
        self.assertEqual(slug3, "/series/solo-leveling")

    def test_bot_app_handlers_registered(self):
        app = setup_telegram_bot()
        # Verify all handlers are registered in group 0
        handlers = app.handlers.get(0, [])
        command_names = set()
        has_callback_handler = False
        has_message_handler = False
        for h in handlers:
            if hasattr(h, "commands"):
                command_names.update(h.commands)
            from telegram.ext import CallbackQueryHandler, MessageHandler
            if isinstance(h, CallbackQueryHandler):
                has_callback_handler = True
            if isinstance(h, MessageHandler):
                has_message_handler = True

        expected_commands = {"start", "help", "add", "bind", "domain", "list", "check", "health", "delete", "remove"}
        self.assertTrue(expected_commands.issubset(command_names))
        self.assertTrue(has_callback_handler)
        self.assertTrue(has_message_handler)

    def test_main_keyboard_layout(self):
        from src.bot.telegram_bot import MAIN_KEYBOARD
        keyboard = MAIN_KEYBOARD.keyboard
        self.assertEqual(len(keyboard), 2)
        row1_texts = [b.text for b in keyboard[0]]
        row2_texts = [b.text for b in keyboard[1]]
        self.assertEqual(row1_texts, ["📚 Daftar Pantauan", "➕ Tambah Komik"])
        self.assertEqual(row2_texts, ["🩺 Status Server", "❓ Panduan"])

    def test_render_manhwa_list_empty(self):
        from src.bot.telegram_bot import render_manhwa_list
        text, markup = render_manhwa_list([], page=1)
        self.assertIn("Daftar target pantauan masih kosong", text)
        self.assertIsNone(markup)

    def test_render_manhwa_list_single_page(self):
        from src.bot.telegram_bot import render_manhwa_list
        mock_manhwas = [
            {"id": i, "canonical_title": f"Manga {i}", "sources": ["ASURA"], "latest_chapter_en": 10, "latest_chapter_id": 5}
            for i in range(1, 4)
        ]
        text, markup = render_manhwa_list(mock_manhwas, page=1)
        self.assertIn("Hal 1/1", text)
        self.assertIn("Manga 1", text)
        self.assertIn("Manga 3", text)
        # 3 delete buttons in 1 row, no pagination nav row
        self.assertEqual(len(markup.inline_keyboard), 1)
        self.assertEqual(len(markup.inline_keyboard[0]), 3)

    def test_render_manhwa_list_pagination(self):
        from src.bot.telegram_bot import render_manhwa_list
        mock_manhwas = [
            {"id": i, "canonical_title": f"Manga {i}", "sources": ["ASURA"], "latest_chapter_en": 10, "latest_chapter_id": 5}
            for i in range(1, 13)
        ]  # 12 items -> 3 pages of (5, 5, 2)
        # Page 1
        text1, markup1 = render_manhwa_list(mock_manhwas, page=1)
        self.assertIn("Hal 1/3", text1)
        self.assertIn("Manga 1", text1)
        self.assertIn("Manga 5", text1)
        self.assertNotIn("Manga 6", text1)
        nav_buttons1 = [b.text for b in markup1.inline_keyboard[-1]]
        self.assertEqual(nav_buttons1, ["📄 1/3", "Selanjutnya ➡️"])

        # Page 2
        text2, markup2 = render_manhwa_list(mock_manhwas, page=2)
        self.assertIn("Hal 2/3", text2)
        self.assertIn("Manga 6", text2)
        self.assertIn("Manga 10", text2)
        nav_buttons2 = [b.text for b in markup2.inline_keyboard[-1]]
        self.assertEqual(nav_buttons2, ["⬅️ Sebelumnya", "📄 2/3", "Selanjutnya ➡️"])

        # Page 3 (Last page)
        text3, markup3 = render_manhwa_list(mock_manhwas, page=3)
        self.assertIn("Hal 3/3", text3)
        self.assertIn("Manga 11", text3)
        self.assertIn("Manga 12", text3)
        nav_buttons3 = [b.text for b in markup3.inline_keyboard[-1]]
        self.assertEqual(nav_buttons3, ["⬅️ Sebelumnya", "📄 3/3"])

        # Clamping test: page 99 should clamp to page 3
        text_clamp, markup_clamp = render_manhwa_list(mock_manhwas, page=99)
        self.assertIn("Hal 3/3", text_clamp)

    def test_is_authorized(self):
        from unittest.mock import MagicMock
        from src.config import Config
        from src.bot.telegram_bot import is_authorized

        # Mock update
        update_admin = MagicMock()
        update_admin.effective_chat.id = 123456

        update_stranger = MagicMock()
        update_stranger.effective_chat.id = 999999

        # Case 1: TELEGRAM_ADMIN_CHAT_ID kosong -> selalu True
        old_admin = Config.TELEGRAM_ADMIN_CHAT_ID
        try:
            Config.TELEGRAM_ADMIN_CHAT_ID = ""
            self.assertTrue(is_authorized(update_admin))
            self.assertTrue(is_authorized(update_stranger))

            # Case 2: TELEGRAM_ADMIN_CHAT_ID diisi -> hanya admin yang lolos
            Config.TELEGRAM_ADMIN_CHAT_ID = "123456"
            self.assertTrue(is_authorized(update_admin))
            self.assertFalse(is_authorized(update_stranger))
        finally:
            Config.TELEGRAM_ADMIN_CHAT_ID = old_admin

    def test_render_manhwa_list_with_filter(self):
        from src.bot.telegram_bot import render_manhwa_list
        mock_manhwas = [
            {"id": 1, "canonical_title": "Solo Leveling", "sources": ["ASURA"], "latest_chapter_en": 180, "latest_chapter_id": 179},
            {"id": 2, "canonical_title": "Omniscient Reader", "sources": ["MANGADEX"], "latest_chapter_en": 210, "latest_chapter_id": 200},
        ]
        text, markup = render_manhwa_list(mock_manhwas, page=1, filter_query="solo")
        self.assertIn("HASIL PENCARIAN", text)
        self.assertIn("Solo Leveling", text)
        self.assertIn("Hal 1/1", text)

    def test_render_manhwa_list_filter_no_match(self):
        from src.bot.telegram_bot import render_manhwa_list
        text, markup = render_manhwa_list([], page=1, filter_query="xyz")
        self.assertIn("Tidak ditemukan manhwa dengan kata kunci", text)
        self.assertIsNone(markup)

    def test_db_get_latest_release_info(self):
        import asyncio
        from src.db import Database
        async def run_async():
            # Inisialisasi SQLite
            Database._engine = "sqlite"
            Database._init_sqlite()
            m_id = await Database.insert_manhwa(None, "Test Check Manhwa", None)
            await Database.record_chapter_log(
                manhwa_id=m_id,
                site_code="ASURA",
                language="EN",
                chapter_num=50.0,
                chapter_raw_title="Chapter 50",
                chapter_url="https://asura.com/ch-50"
            )
            rel = await Database.get_latest_release_info(m_id)
            self.assertIsNotNone(rel)
            self.assertEqual(rel["chapter_num"], 50.0)
            self.assertEqual(rel["site_code"], "ASURA")
            # Cleanup
            await Database.delete_manhwa(m_id)
        asyncio.run(run_async())

if __name__ == "__main__":
    unittest.main()

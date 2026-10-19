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

        expected_commands = {"start", "help", "add", "bind", "domain", "list", "health", "delete", "remove"}
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

if __name__ == "__main__":
    unittest.main()

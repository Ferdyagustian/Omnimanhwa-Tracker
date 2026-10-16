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
        for h in handlers:
            if hasattr(h, "commands"):
                command_names.update(h.commands)

        expected_commands = {"start", "help", "add", "bind", "domain", "list", "health", "delete", "remove"}
        self.assertTrue(expected_commands.issubset(command_names))

if __name__ == "__main__":
    unittest.main()

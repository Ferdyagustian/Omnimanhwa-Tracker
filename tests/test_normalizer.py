import unittest
from src.normalizer import normalize_title, parse_chapter_info

class TestNormalizer(unittest.TestCase):
    def test_normalize_title_basic(self):
        self.assertEqual(normalize_title("Solo Leveling"), "solo leveling")
        self.assertEqual(normalize_title("  Solo   Leveling  "), "solo leveling")

    def test_normalize_title_stopwords_and_punctuations(self):
        self.assertEqual(
            normalize_title("Solo Leveling (Manhwa) Sub Indo!"),
            "solo leveling"
        )
        self.assertEqual(
            normalize_title("Komik Return of the Mount Hua Sect - Bahasa Indonesia [RAW]"),
            "return of the mount hua sect"
        )

    def test_parse_chapter_info_standard(self):
        ch, special, raw = parse_chapter_info("Chapter 189")
        self.assertEqual(ch, 189.0)
        self.assertFalse(special)

        ch, special, raw = parse_chapter_info("Ch. 89.5 - Extra")
        self.assertEqual(ch, 89.5)
        self.assertTrue(special)

    def test_parse_chapter_info_season_reset(self):
        ch, special, raw = parse_chapter_info("Season 2 Episode 1 - The Return")
        self.assertEqual(ch, 1.0)
        self.assertTrue(special)

    def test_parse_chapter_info_side_story(self):
        ch, special, raw = parse_chapter_info("Side Story 5")
        self.assertEqual(ch, 5.0)
        self.assertTrue(special)

    def test_parse_chapter_info_empty(self):
        ch, special, raw = parse_chapter_info("")
        self.assertIsNone(ch)
        self.assertFalse(special)

    def test_parse_chapter_info_calendar_year(self):
        # Tanpa kata kunci 'chapter/ch/ep', angka tahun kalender (1900-2099) diabaikan
        ch, special, _ = parse_chapter_info("Special 2024")
        self.assertIsNone(ch)
        self.assertTrue(special)

        # Jika ada kata kunci 'chapter/episode', angka tetap diekstrak dengan benar
        ch, special, _ = parse_chapter_info("Episode 45 (2024)")
        self.assertEqual(ch, 45.0)

        ch, special, _ = parse_chapter_info("Chapter 2000")
        self.assertEqual(ch, 2000.0)

if __name__ == "__main__":
    unittest.main()

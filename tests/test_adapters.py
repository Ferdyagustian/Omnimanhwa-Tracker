import unittest
import asyncio
from unittest.mock import patch
from selectolax.lexbor import LexborHTMLParser as HTMLParser
from src.adapters.asura import AsuraAdapter
from src.adapters.komiku import KomikuAdapter
from src.adapters.vortex import VortexAdapter
from src.adapters.mgeko import MgekoAdapter

class TestAdaptersParsing(unittest.TestCase):
    def test_asura_parsing(self):
        adapter = AsuraAdapter(base_url="https://asuracomic.net")
        mock_html = """
        <div class="chapters">
            <a href="/series/solo-leveling-chapter-200">Chapter 200</a>
            <a href="/series/solo-leveling-chapter-199-5">Chapter 199.5 - Side Story</a>
            <a href="/series/solo-leveling-chapter-198">Chapter 198</a>
        </div>
        """
        with patch.object(adapter, "get_html", return_value=(HTMLParser(mock_html), None, 200)):
            chapters = asyncio.run(adapter.get_latest_chapters("/series/solo-leveling"))
            self.assertEqual(len(chapters), 3)
            self.assertEqual(chapters[0]["chapter_num"], 200.0)
            self.assertEqual(chapters[1]["chapter_num"], 199.5)
            self.assertTrue(chapters[1]["is_special"])
            self.assertEqual(chapters[2]["chapter_num"], 198.0)
            self.assertEqual(chapters[0]["chapter_url"], "https://asuracomic.net/series/solo-leveling-chapter-200")

    def test_komiku_parsing(self):
        adapter = KomikuAdapter(base_url="https://komiku.org")
        mock_html = """
        <table id="Daftar_Chapter">
            <td class="judulseries"><a href="/ch/solo-leveling-chapter-180-indo/">Chapter 180 Indo</a></td>
            <td class="judulseries"><a href="/ch/solo-leveling-chapter-179-indo/">Chapter 179</a></td>
        </table>
        """
        with patch.object(adapter, "get_html", return_value=(HTMLParser(mock_html), None, 200)):
            chapters = asyncio.run(adapter.get_latest_chapters("/manga/solo-leveling"))
            self.assertEqual(len(chapters), 2)
            self.assertEqual(chapters[0]["chapter_num"], 180.0)
            self.assertEqual(chapters[1]["chapter_num"], 179.0)
            self.assertEqual(chapters[0]["chapter_url"], "https://komiku.org/ch/solo-leveling-chapter-180-indo/")

    def test_vortex_parsing(self):
        adapter = VortexAdapter(base_url="https://vortexscans.org")
        mock_html = """
        <div class="chapter-list">
            <a href="https://vortexscans.org/series/nano-machine/chapter-150">Chapter 150</a>
            <a href="https://vortexscans.org/series/nano-machine/chapter-149">Chapter 149</a>
        </div>
        """
        with patch.object(adapter, "get_html", return_value=(HTMLParser(mock_html), None, 200)):
            chapters = asyncio.run(adapter.get_latest_chapters("/series/nano-machine"))
            self.assertEqual(len(chapters), 2)
            self.assertEqual(chapters[0]["chapter_num"], 150.0)

    def test_mgeko_parsing(self):
        adapter = MgekoAdapter(base_url="https://www.mgeko.cc")
        mock_html = """
        <div class="chapter-list">
            <a href="/reader/en/solo-leveling-chapter-110-eng-li/">Chapter 110</a>
            <a href="/reader/en/solo-leveling-chapter-109-eng-li/">Chapter 109</a>
        </div>
        """
        with patch.object(adapter, "get_html", return_value=(HTMLParser(mock_html), None, 200)):
            chapters = asyncio.run(adapter.get_latest_chapters("/jumbo/manga/solo-leveling"))
            self.assertEqual(len(chapters), 2)
            self.assertEqual(chapters[0]["chapter_num"], 110.0)
            self.assertEqual(chapters[0]["chapter_url"], "https://www.mgeko.cc/reader/en/solo-leveling-chapter-110-eng-li/")

if __name__ == "__main__":
    unittest.main()

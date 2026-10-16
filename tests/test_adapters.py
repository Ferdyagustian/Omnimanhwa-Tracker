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
            <a href="https://vortexscans.org/series/the-saint/chapter-43_01">Chapter 43 New</a>
            <a href="https://vortexscans.org/series/the-saint/chapter-42">Chapter 42</a>
        </div>
        """
        with patch.object(adapter, "get_html", return_value=(HTMLParser(mock_html), None, 200)):
            # Uji juga normalisasi jika input berupa url chapter
            chapters = asyncio.run(adapter.get_latest_chapters("/series/the-saint/chapter-43_01"))
            self.assertEqual(len(chapters), 2)
            self.assertEqual(chapters[0]["chapter_num"], 43.0)
            self.assertEqual(chapters[1]["chapter_num"], 42.0)
            self.assertEqual(chapters[0]["chapter_url"], "https://vortexscans.org/series/the-saint/chapter-43_01")
            self.assertEqual(chapters[1]["chapter_url"], "https://vortexscans.org/series/the-saint/chapter-42")

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

    def test_mgeko_search(self):
        adapter = MgekoAdapter(base_url="https://www.mgeko.cc")
        mock_html = """
        <div class="comic-list">
            <a href="/jumbo/manga/solo-leveling" title="Solo Leveling">
                <img src="https://www.mgeko.cc/cover.jpg" />
                Solo Leveling
            </a>
        </div>
        """
        with patch.object(adapter, "get_html", return_value=(HTMLParser(mock_html), None, 200)):
            results = asyncio.run(adapter.search_comics("Solo Leveling"))
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["slug"], "/jumbo/manga/solo-leveling")
            self.assertEqual(results[0]["title"], "Solo Leveling")
            self.assertEqual(results[0]["cover_url"], "https://www.mgeko.cc/cover.jpg")

    def test_komiku_search(self):
        adapter = KomikuAdapter(base_url="https://komiku.org")
        mock_html = """
        <div class="bge">
            <a href="/manga/solo-leveling/">
                <h4>Solo Leveling</h4>
            </a>
        </div>
        """
        with patch.object(adapter, "get_html", return_value=(HTMLParser(mock_html), None, 200)):
            results = asyncio.run(adapter.search_comics("Solo Leveling"))
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["slug"], "/manga/solo-leveling/")
            self.assertEqual(results[0]["title"], "Solo Leveling")

    def test_vortex_search(self):
        adapter = VortexAdapter(base_url="https://vortexscans.org")
        mock_html = """
        <div class="series-list">
            <a href="/series/the-saint" title="The Saint Levels Up Through Necromancy">Manhwa</a>
            <a href="/series/the-saint" title="The Saint Levels Up Through Necromancy">The Saint Levels Up Through Necromancy</a>
        </div>
        """
        with patch.object(adapter, "get_html", return_value=(HTMLParser(mock_html), None, 200)):
            results = asyncio.run(adapter.search_comics("The Saint Levels Up"))
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["slug"], "/series/the-saint")
            self.assertEqual(results[0]["title"], "The Saint Levels Up Through Necromancy")

    def test_asura_search(self):
        adapter = AsuraAdapter(base_url="https://asurascans.com")
        mock_html = """
        <div class="grid">
            <a href="https://asurascans.com/comics/solo-leveling-1234">Solo Leveling</a>
        </div>
        """
        with patch.object(adapter, "get_html", return_value=(HTMLParser(mock_html), None, 200)):
            results = asyncio.run(adapter.search_comics("Solo Leveling"))
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]["slug"], "/comics/solo-leveling-1234")
            self.assertEqual(results[0]["title"], "Solo Leveling")

if __name__ == "__main__":
    unittest.main()

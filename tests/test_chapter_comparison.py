import os
import unittest
import asyncio
from src.db import Database, SQLITE_DB_PATH

class TestChapterComparisonAndDeduplication(unittest.TestCase):
    def setUp(self):
        # Gunakan database SQLite lokal untuk testing
        Database._pool = "sqlite"
        Database._engine = "sqlite"
        if os.path.exists(SQLITE_DB_PATH):
            os.remove(SQLITE_DB_PATH)
        Database._init_sqlite()

    def test_multi_site_deduplication_and_priority(self):
        async def run_test():
            # 1. Tambah manhwa baru
            manhwa_id = await Database.insert_manhwa(
                mangadex_uuid=None,
                canonical_title="Omni Test Solo Leveling",
                cover_image_url="https://example.com/cover.jpg"
            )
            await Database.bind_source(manhwa_id, "MGEKO", "/jumbo/manga/solo-leveling")
            await Database.bind_source(manhwa_id, "MANGADEX", "/title/test-uuid")
            await Database.bind_source(manhwa_id, "KOMIKU", "/manga/solo-leveling")

            # Skenario 1: Mgeko update Ch 49 pertama kali -> Harus bernilai True (notifikasi dikirim)
            res1 = await Database.record_chapter_log(
                manhwa_id=manhwa_id,
                site_code="MGEKO",
                language="EN",
                chapter_num=49.0,
                chapter_raw_title="Chapter 49",
                chapter_url="https://www.mgeko.cc/ch49"
            )
            self.assertTrue(res1, "Mgeko Ch 49 pertama kali harus mengirimkan notifikasi")

            # Skenario 2: MangaDex update tetapi hanya Ch 2 -> Harus False (diabaikan karena kadaluwarsa dibanding Ch 49)
            res2 = await Database.record_chapter_log(
                manhwa_id=manhwa_id,
                site_code="MANGADEX",
                language="EN",
                chapter_num=2.0,
                chapter_raw_title="Chapter 2",
                chapter_url="https://mangadex.org/ch2"
            )
            self.assertFalse(res2, "MangaDex Ch 2 harus diabaikan karena tertinggal dari Ch 49")

            # Skenario 3: MangaDex menyusul merilis Ch 49 yang sama -> Harus False (tidak boleh notif duplikat)
            res3 = await Database.record_chapter_log(
                manhwa_id=manhwa_id,
                site_code="MANGADEX",
                language="EN",
                chapter_num=49.0,
                chapter_raw_title="Chapter 49",
                chapter_url="https://mangadex.org/ch49"
            )
            self.assertFalse(res3, "MangaDex Ch 49 tidak boleh mengirim notifikasi duplikat karena Mgeko sudah rilis lebih dulu")

            # Skenario 4: MangaDex ternyata rilis Ch 50 lebih dulu -> Harus True (notifikasi dikirim dari MangaDex)
            res4 = await Database.record_chapter_log(
                manhwa_id=manhwa_id,
                site_code="MANGADEX",
                language="EN",
                chapter_num=50.0,
                chapter_raw_title="Chapter 50",
                chapter_url="https://mangadex.org/ch50"
            )
            self.assertTrue(res4, "MangaDex Ch 50 yang rilis baru harus mengirimkan notifikasi")

            # Skenario 5: Mgeko kemudian merilis Ch 50 yang sama -> Harus False (MangaDex sudah menotifikasi Ch 50)
            res5 = await Database.record_chapter_log(
                manhwa_id=manhwa_id,
                site_code="MGEKO",
                language="EN",
                chapter_num=50.0,
                chapter_raw_title="Chapter 50",
                chapter_url="https://www.mgeko.cc/ch50"
            )
            self.assertFalse(res5, "Mgeko Ch 50 tidak boleh kirim duplikat jika MangaDex sudah menotifikasi lebih awal")

            # Skenario 6: Komiku merilis Ch 49 versi Bahasa Indonesia (ID) -> Harus True (bahasa berbeda tidak diblokir)
            res6 = await Database.record_chapter_log(
                manhwa_id=manhwa_id,
                site_code="KOMIKU",
                language="ID",
                chapter_num=49.0,
                chapter_raw_title="Chapter 49 Indo",
                chapter_url="https://komiku.org/ch49"
            )
            self.assertTrue(res6, "Rilis bahasa Indonesia (ID) tidak boleh diblokir oleh rilis bahasa Inggris (EN)")

        asyncio.run(run_test())

    def test_cleanup_old_chapter_logs(self):
        async def run_test():
            manhwa_id = await Database.insert_manhwa(None, "Retention Test", None)
            await Database.record_chapter_log(manhwa_id, "MGEKO", "EN", 1.0, "Ch 1", "https://mgeko.cc/1")
            
            # Ubah notified_at secara manual menjadi 35 hari yang lalu
            import sqlite3
            conn = sqlite3.connect(SQLITE_DB_PATH)
            conn.execute("UPDATE chapter_logs SET notified_at = datetime('now', '-35 days') WHERE chapter_num = 1.0")
            conn.commit()
            conn.close()

            # Bersihkan log yang berusia > 30 hari
            deleted = await Database.cleanup_old_chapter_logs(days=30)
            self.assertEqual(deleted, 1, "Log berusia 35 hari harus terhapus")

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()

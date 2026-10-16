# OmniManhwa Tracker Engine (OMTE) v1.2

> **Sistem Pelacak Rilis Chapter Manhwa 24/7, Multi-Site Auto-Discovery, & AI-Assisted Alias Resolver.**  
> Dirancang dengan arsitektur hemat sumber daya (*battle-tested* untuk lingkungan Cloud VM 1 GB RAM & 4 GB Swap).

---

## 🌟 Fitur Utama

- **Multi-Site Concurrent Auto-Discovery**: Pendaftaran target cukup dengan satu perintah `/add [judul]`. Engine memindai seluruh situs (MangaDex, Mgeko, VortexScans, AsuraScans, Komiku) secara paralel dan mengaitkan seluruh sumber yang cocok secara otomatis.
- **3-Tier Entity Resolution**: Pipeline pencocokan judul cerdas berbasis *Exact Normalized Match*, *RapidFuzz Token Scoring*, dan *Google Gemini Flash AI Disambiguator* untuk variasi judul bahasa Korea, Inggris, dan Indonesia.
- **Smart Chapter Priority & Multi-Site Deduplication**: 
  - Membandingkan progres chapter antar sumber yang terikat.
  - Memprioritaskan sumber rilis tercepat/terdepan dan mengabaikan chapter kadaluwarsa.
  - Mendeduplikasi notifikasi secara global per `(manhwa_id, language, chapter_num)`, sehingga rilis nomor chapter yang sama dari situs lain tidak menimbulkan notifikasi duplikat.
  - Pemisahan pemantauan rilis Bahasa Inggris (`EN`) dan Bahasa Indonesia (`ID`).
- **Anti-Bot & Etika Jaringan**:
  - Polling berkala 20 menit dengan **Random Jitter** (10–35 detik).
  - Rotasi User-Agent Chrome modern dinamis.
  - TLS impersonation Chrome via `curl_cffi` hemat memori (tanpa headless browser berat).
- **Data Hygiene & Health Monitoring**:
  - Pembersihan otomatis (*data retention*) untuk log rilis yang berusia lebih dari 30 hari.
  - Pemantauan real-time status RAM, Swap, dan database via perintah `/health`.

---

## 🏛️ Matriks Sumber Data (Adapters)

| Situs | Kode | Bahasa | Prioritas Polling | Metode Akses |
| :--- | :---: | :---: | :---: | :--- |
| **Mgeko** | `MGEKO` | EN | 1 | `curl_cffi` + Selectolax HTML Parser |
| **MangaDex** | `MANGADEX` | MULTI | 2 | Official REST API (`api.mangadex.org`) |
| **VortexScans** | `VORTEX` | EN | 3 | `curl_cffi` + Selectolax HTML Parser |
| **AsuraScans** | `ASURA` | EN | 4 | `curl_cffi` + Selectolax / Next.js State |
| **Komiku** | `KOMIKU` | ID | 5 | `curl_cffi` + Selectolax HTML Parser |

---

## 🤖 Perintah Telegram Bot

| Perintah | Deskripsi | Contoh |
| :--- | :--- | :--- |
| `/add [judul / URL]` | Memindai seluruh website dan mendaftarkan manhwa ke target pantauan | `/add Solo Leveling` |
| `/list` | Menampilkan seluruh target manhwa, sumber terikat, dan status rilis terakhir | `/list` |
| `/bind [id] [situs] [slug]` | Menautkan link atau slug sumber tertentu secara manual | `/bind 1 KOMIKU /manga/solo-leveling` |
| `/delete [id]` | Menghapus target manhwa dan seluruh riwayat sumbernya | `/delete 1` |
| `/domain [situs] [new_url]`| Memperbarui alamat base URL jika situs melakukan redirect domain | `/domain ASURA https://asuracomic.net` |
| `/health` | Memeriksa beban CPU/RAM, Swap Memory, dan status koneksi database | `/health` |

---

## 🚀 Panduan Menjalankan

### 1. Menjalankan via Docker Compose (Rekomendasi Produksi)

```bash
# 1. Salin template konfigurasi environment
cp .env.example .env

# 2. Isi TELEGRAM_BOT_TOKEN dan TELEGRAM_ADMIN_CHAT_ID pada file .env
nano .env

# 3. Jalankan container dengan pembatasan memori otomatis
docker compose up -d --build

# 4. Periksa log container
docker compose logs -f omte-core
```

### 2. Menjalankan Secara Lokal (Development / SQLite Fallback)

```bash
# 1. Pasang dependensi
pip install -r requirements.txt

# 2. Jalankan test suite otomatis
python -m unittest discover tests

# 3. Jalankan engine utama
python -m src.main
```

---

## 📁 Struktur Direktori

```text
omnimanhwa/
├── src/
│   ├── adapters/          # Modul scraper per website (MangaDex, Asura, Mgeko, Vortex, Komiku)
│   ├── bot/               # Telegram bot handlers & notification dispatcher
│   ├── resolver/          # 3-tier matcher & Gemini semantic disambiguator
│   ├── config.py          # Konfigurasi aplikasi & environment variables
│   ├── db.py              # Layer database (PostgreSQL asyncpg + SQLite fallback)
│   ├── main.py            # Entry point & background tracker worker loop
│   └── normalizer.py      # Ekstraksi angka chapter, regex, & title normalizer
├── tests/                 # Unit tests (24 test cases lengkap)
├── docker-compose.yml     # Orkestrasi Docker (dengan mem_limit ketat)
├── Dockerfile             # Multi-stage Docker image
├── init.sql               # Skema PostgreSQL & indeks retensi
└── requirements.txt       # Dependensi Python minimal
```

---

## 📄 Lisensi

Proyek ini dilisensikan di bawah lisensi MIT.

# OmniManhwa Tracker Engine (OMTE) v1.2

> **24/7 Manhwa Chapter Release Tracker, Multi-Site Auto-Discovery, & AI-Assisted Alias Resolver.**  
> Engineered with a lightweight, resource-efficient architecture (*battle-tested* on 1 GB RAM & 4 GB Swap Cloud VMs).

---

## ✨ Key Features

- **Multi-Site Concurrent Auto-Discovery**: Register targets with a single `/add [title]` command. The engine concurrently scans all supported sites (MangaDex, Mgeko, VortexScans, AsuraScans, Komiku) and automatically binds all matching sources.
- **3-Tier Entity Resolution**: Intelligent title-matching pipeline powered by *Exact Normalized Match*, *RapidFuzz Token Scoring*, and a *Google Gemini Flash AI Disambiguator* to accurately resolve Korean, English, and Indonesian title variations.
- **Smart Chapter Priority & Multi-Site Deduplication**: 
  - Compares chapter progress across all bound sources.
  - Prioritizes the fastest/most ahead release source and ignores outdated chapters.
  - Globally deduplicates notifications per `(manhwa_id, language, chapter_num)`, preventing duplicate alerts when other sites release the same chapter later.
  - Independent release tracking for English (`EN`) and Indonesian (`ID`) translations.
- **Anti-Bot Evasion & Network Etiquette**:
  - 20-minute periodic polling interval with **Random Jitter** (10–35 seconds).
  - Dynamic modern Chrome User-Agent rotation.
  - Memory-efficient Chrome TLS fingerprint impersonation via `curl_cffi` (no heavy headless browsers required).
- **Data Hygiene & Health Monitoring**:
  - Automated data retention cleanup for release logs older than 30 days.
  - Real-time RAM, Swap, and database health monitoring via the `/health` command.

---

## 🏛️ Data Source Matrix (Adapters)

| Site | Code | Language | Polling Priority | Access Method |
| :--- | :---: | :---: | :---: | :--- |
| **Mgeko** | `MGEKO` | EN | 1 | `curl_cffi` + Selectolax HTML Parser |
| **MangaDex** | `MANGADEX` | MULTI | 2 | Official REST API (`api.mangadex.org`) |
| **VortexScans** | `VORTEX` | EN | 3 | `curl_cffi` + Selectolax HTML Parser |
| **AsuraScans** | `ASURA` | EN | 4 | `curl_cffi` + Selectolax / Next.js State |
| **Komiku** | `KOMIKU` | ID | 5 | `curl_cffi` + Selectolax HTML Parser |

---

## 🤖 Telegram Bot Commands

| Command | Description | Example |
| :--- | :--- | :--- |
| `/add [title / URL]` | Scans all supported websites and adds the manhwa to the watchlist | `/add Solo Leveling` |
| `/list [page / title]` | Displays tracked manhwa with pagination jump or title keyword search | `/list solo` or `/list 3` |
| `/check [id]` | Checks latest released chapter, detected timestamp, and source links | `/check 1` |
| `/bind [id] [site] [slug]` | Manually binds a specific source URL or slug to an existing target | `/bind 1 KOMIKU /manga/solo-leveling` |
| `/delete [id]` | Deletes a tracked manhwa and all associated source history | `/delete 1` |
| `/domain [site] [new_url]`| Updates the base URL if a source site changes or redirects its domain | `/domain ASURA https://asuracomic.net` |
| `/health` | Checks CPU/RAM load, Swap memory usage, and database connection status | `/health` |

---

## 🚀 Getting Started

### 1. Run via Docker Compose (Recommended for Production)

```bash
# 1. Copy the environment configuration template
cp .env.example .env

# 2. Fill in TELEGRAM_BOT_TOKEN and TELEGRAM_ADMIN_CHAT_ID in the .env file
nano .env

# 3. Start the container with automated memory limits
docker compose up -d --build

# 4. Monitor container logs
docker compose logs -f omte-core
```

### Updating / Redeploying on the Server

```bash
git pull origin main
docker compose up -d --build omte-core
```

### 2. Run Locally (Development / SQLite Fallback)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the automated test suite
python -m unittest discover tests

# 3. Start the core engine
python -m src.main
```

---

## 📁 Directory Structure

```text
omnimanhwa/
├── src/
│   ├── adapters/          # Site-specific scraper modules (MangaDex, Asura, Mgeko, Vortex, Komiku)
│   ├── bot/               # Telegram bot handlers & notification dispatcher
│   ├── resolver/          # 3-tier matcher & Gemini semantic disambiguator
│   ├── config.py          # Application configuration & environment variables
│   ├── db.py              # Database layer (PostgreSQL asyncpg + SQLite fallback)
│   ├── main.py            # Application entry point & background tracker worker loop
│   └── normalizer.py      # Chapter number extraction, regex rules, & title normalizer
├── tests/                 # Unit tests (34 comprehensive test cases)
├── docker-compose.yml     # Docker orchestration (with strict mem_limit)
├── Dockerfile             # Multi-stage Docker image build
├── init.sql               # PostgreSQL schema & retention indexes
└── requirements.txt       # Minimal Python dependencies
```

---

## 📄 License

This project is licensed under the MIT License.
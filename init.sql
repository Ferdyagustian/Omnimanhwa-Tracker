-- OmniManhwa Tracker Engine (OMTE) Schema v1.2
-- PostgreSQL Initialization & Seeding Script

-- 1. Tabel Konfigurasi Situs
CREATE TABLE IF NOT EXISTS site_configs (
    site_code VARCHAR(20) PRIMARY KEY,
    base_url VARCHAR(255) NOT NULL,
    language VARCHAR(5) NOT NULL,
    poll_interval_minutes INT DEFAULT 15,
    is_active BOOLEAN DEFAULT TRUE,
    consecutive_failures INT DEFAULT 0,
    last_polled_at TIMESTAMPTZ,
    cf_clearance_cookie TEXT,
    cf_user_agent TEXT,
    cf_cookie_expires_at TIMESTAMPTZ,
    proxy_url TEXT
);

-- Seed Data Situs Awal
INSERT INTO site_configs (site_code, base_url, language, poll_interval_minutes)
VALUES 
    ('MGEKO', 'https://www.mgeko.cc', 'EN', 15),
    ('MANGADEX', 'https://mangadex.org', 'MULTI', 15),
    ('VORTEX', 'https://vortexscans.org', 'EN', 10),
    ('ASURA', 'https://asurascans.com', 'EN', 10),
    ('KOMIKU', 'https://komiku.org', 'ID', 15)
ON CONFLICT (site_code) DO NOTHING;

-- 2. Tabel Entitas Utama Manhwa
CREATE TABLE IF NOT EXISTS manhwas (
    id SERIAL PRIMARY KEY,
    mangadex_uuid UUID UNIQUE,
    canonical_title VARCHAR(255) NOT NULL,
    cover_image_url TEXT,
    latest_chapter_en NUMERIC(6, 2) DEFAULT 0,
    latest_chapter_id NUMERIC(6, 2) DEFAULT 0,
    is_tracking BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. Tabel Variasi Nama / Alias
CREATE TABLE IF NOT EXISTS manhwa_aliases (
    id SERIAL PRIMARY KEY,
    manhwa_id INT REFERENCES manhwas(id) ON DELETE CASCADE,
    alias_title VARCHAR(255) NOT NULL,
    normalized_title VARCHAR(255) NOT NULL,
    lang_code VARCHAR(10),
    UNIQUE(manhwa_id, normalized_title)
);
CREATE INDEX IF NOT EXISTS idx_aliases_normalized ON manhwa_aliases(normalized_title);

-- 4. Tabel Pemetaan Sumber Website per Manhwa
CREATE TABLE IF NOT EXISTS manhwa_sources (
    id SERIAL PRIMARY KEY,
    manhwa_id INT REFERENCES manhwas(id) ON DELETE CASCADE,
    site_code VARCHAR(20) REFERENCES site_configs(site_code),
    relative_slug VARCHAR(500) NOT NULL,
    last_chapter_num NUMERIC(6, 2) DEFAULT 0,
    last_chapter_url TEXT,
    last_checked_at TIMESTAMPTZ,
    UNIQUE(manhwa_id, site_code)
);

-- 5. Tabel Riwayat Rilis & Log Notifikasi
CREATE TABLE IF NOT EXISTS chapter_logs (
    id SERIAL PRIMARY KEY,
    manhwa_id INT REFERENCES manhwas(id) ON DELETE CASCADE,
    site_code VARCHAR(20) REFERENCES site_configs(site_code),
    language VARCHAR(5) NOT NULL,
    chapter_num NUMERIC(6, 2) NOT NULL,
    chapter_raw_title VARCHAR(255),
    chapter_url TEXT NOT NULL,
    notified_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_chapter_notification UNIQUE(manhwa_id, site_code, chapter_url)
);
CREATE INDEX IF NOT EXISTS idx_chapter_logs_notified ON chapter_logs(notified_at);

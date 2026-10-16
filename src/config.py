import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Database
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "omnimanhwa")
    DB_USER = os.getenv("DB_USER", "omniuser")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "omnipassword123")

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_ADMIN_CHAT_ID = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "")

    # Gemini
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

    # Network & Proxy
    PROXY_URL = os.getenv("PROXY_URL", "")

    # Engine
    POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "20"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    @classmethod
    def get_db_dsn(cls) -> str:
        # Safe URL encoding untuk username dan password yang mengandung karakter khusus
        user = quote_plus(cls.DB_USER)
        password = quote_plus(cls.DB_PASSWORD)
        return f"postgresql://{user}:{password}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"

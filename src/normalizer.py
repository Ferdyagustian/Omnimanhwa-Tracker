import re
from typing import Optional, Tuple

STOP_WORDS = [
    r"\bmanhwa\b",
    r"\bmanhua\b",
    r"\bmanga\b",
    r"\bkomik\b",
    r"\bwebtoon\b",
    r"\bsub\s*indo\b",
    r"\bbahasa\s*indonesia\b",
    r"\braw\b",
]

def normalize_title(title: str) -> str:
    """
    Normalisasi judul manhwa:
    1. Lowercase
    2. Hapus stop words umum
    3. Hapus tanda baca & karakter khusus
    4. Rapatkan spasi ganda
    """
    if not title:
        return ""
    text = title.lower()
    for pattern in STOP_WORDS:
        text = re.sub(pattern, " ", text)
    # Hapus semua karakter non-alphanumeric kecuali spasi
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    # Bersihkan multiple spasi
    text = re.sub(r"\s+", " ", text).strip()
    return text

def parse_chapter_info(title_or_text: str) -> Tuple[Optional[float], bool, str]:
    """
    Ekstrak nomor chapter dan deteksi penanda khusus (Season baru / Side Story).
    Returns: (chapter_num, is_special_or_new_season, raw_tag)
    """
    if not title_or_text:
        return None, False, ""
    
    text = title_or_text.strip()
    
    # Deteksi Season Baru atau Side Story / Prologue
    is_special = bool(
        re.search(r"\b(season\s*\d+|s\d+|side\s*story|extra|prologue|epilogue|end|finale)\b", text, re.IGNORECASE)
    )
    
    # Regex ekstraksi angka chapter (e.g., "Chapter 123.5", "Ch. 89", "Ch 12", "Episode 45")
    # Cari pola kata chapter/ch/ep diikuti angka
    match = re.search(r"(?:chapter|ch\.?|ep\.?|episode)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if match:
        try:
            return float(match.group(1)), is_special, text
        except ValueError:
            pass
            
    # Fallback: cari angka desimal/bulat pertama yang berdiri sendiri
    fallback_match = re.search(r"\b(\d+(?:\.\d+)?)\b", text)
    if fallback_match:
        try:
            return float(fallback_match.group(1)), is_special, text
        except ValueError:
            pass

    return None, is_special, text

import json
import logging
from typing import List, Optional
import aiohttp
from src.config import Config

logger = logging.getLogger(__name__)

GEMINI_CANDIDATE_MODELS = [
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-flash-latest"
]

class AIDisambiguator:
    @staticmethod
    async def disambiguate(
        target_title: str,
        canonical_title: str,
        known_aliases: Optional[List[str]] = None,
        synopsis: Optional[str] = None
    ) -> bool:
        """
        Memeriksa apakah target_title adalah manhwa yang sama dengan canonical_title.
        HANYA dipanggil saat skor RapidFuzz berada di rentang abu-abu (60.0 - 87.9) pada saat /add.
        """
        api_key = Config.GEMINI_API_KEY
        if not api_key:
            logger.warning("GEMINI_API_KEY tidak ditemukan. Melewati AI disambiguation.")
            return False

        aliases_text = ", ".join(known_aliases) if known_aliases else "Tidak ada"
        prompt = (
            f"Anda adalah sistem AI Entity Resolution untuk judul komik/manhwa.\n"
            f"Tugas: Tentukan apakah 'Judul Kandidat' adalah manhwa yang sama dengan 'Judul Kanonikal'.\n\n"
            f"- Judul Kandidat: {target_title}\n"
            f"- Judul Kanonikal: {canonical_title}\n"
            f"- Variasi Nama yang Diketahui: {aliases_text}\n"
        )
        if synopsis:
            prompt += f"- Sinopsis Singkat: {synopsis[:300]}\n"

        prompt += (
            "\nKeluarkan respons HANYA dalam format JSON berikut:\n"
            "{\n"
            '  "is_match": true atau false,\n'
            '  "confidence": angka 0.0 sampai 1.0,\n'
            '  "reason": "alasan singkat 1 kalimat"\n'
            "}"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.1
            }
        }

        async with aiohttp.ClientSession() as session:
            for model_name in GEMINI_CANDIDATE_MODELS:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                try:
                    async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            candidates = data.get("candidates", [])
                            if not candidates:
                                continue
                            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                            parsed = json.loads(raw_text)
                            is_match = parsed.get("is_match", False)
                            confidence = float(parsed.get("confidence", 0.0))
                            reason = parsed.get("reason", "")
                            logger.info(f"[AI Disambiguator ({model_name})] Match: {is_match} (conf: {confidence}) - {reason}")
                            return is_match and confidence >= 0.75
                        else:
                            logger.warning(f"Gemini API ({model_name}) error {resp.status}, mencoba model alternatif...")
                except Exception as e:
                    logger.warning(f"Error memanggil Gemini ({model_name}): {e}")

        logger.error("[AI Disambiguator] Semua model alternatif gagal dihubungi.")
        return False

if __name__ == "__main__":
    import asyncio
    async def test():
        # Uji coba kecocokan judul romanisasi vs judul inggris
        result = await AIDisambiguator.disambiguate(
            target_title="Na Honjaman Lebel-eob",
            canonical_title="Solo Leveling",
            known_aliases=["I Alone Level Up", "Only I Level Up"]
        )
        print("Self-check AI Disambiguator result (Solo Leveling vs Na Honjaman Lebel-eob):", result)
        assert result is True, "AI should identify Solo Leveling as the same manhwa"
        print("AI Disambiguator passed successfully!")
    asyncio.run(test())

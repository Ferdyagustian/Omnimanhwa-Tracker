import logging
from typing import List, Dict, Any, Tuple
from rapidfuzz import fuzz
from src.normalizer import normalize_title
from src.resolver.ai_disambiguator import AIDisambiguator

logger = logging.getLogger(__name__)

class EntityMatcher:
    @staticmethod
    def fuzzy_score(candidate_norm: str, target_norm: str) -> float:
        """
        Kombinasi skor RapidFuzz: token_sort_ratio dan WRatio.
        """
        score_w = fuzz.WRatio(candidate_norm, target_norm)
        score_ts = fuzz.token_sort_ratio(candidate_norm, target_norm)
        return round(max(score_w, score_ts), 2)

    @classmethod
    async def match_candidate(
        cls,
        candidate_title: str,
        canonical_title: str,
        known_aliases: List[str],
        synopsis: str = ""
    ) -> Tuple[bool, float, str]:
        """
        3-Tier Matching Pipeline:
        1. Exact match (100.0)
        2. RapidFuzz (>= 88.0: Auto, < 60.0: Reject)
        3. AI Semantic Disambiguator (60.0 - 87.9)
        Returns: (is_match, score, match_type)
        """
        cand_norm = normalize_title(candidate_title)
        canon_norm = normalize_title(canonical_title)

        # Lapis 1: Exact Normalized Match
        if cand_norm == canon_norm:
            return True, 100.0, "exact"

        for alias in known_aliases:
            if cand_norm == normalize_title(alias):
                return True, 100.0, "exact_alias"

        # Lapis 2: RapidFuzz Scoring
        best_score = cls.fuzzy_score(cand_norm, canon_norm)
        for alias in known_aliases:
            score = cls.fuzzy_score(cand_norm, normalize_title(alias))
            if score > best_score:
                best_score = score

        if best_score >= 88.0:
            return True, best_score, "rapidfuzz_high"

        if best_score < 60.0:
            return False, best_score, "rapidfuzz_low"

        # Lapis 3: AI Semantic Disambiguator (Rentang 60.0 - 87.9)
        logger.info(f"Fuzzy score {best_score} di zona abu-abu untuk '{candidate_title}'. Memanggil AI...")
        ai_match = await AIDisambiguator.disambiguate(
            target_title=candidate_title,
            canonical_title=canonical_title,
            known_aliases=known_aliases,
            synopsis=synopsis
        )
        return ai_match, best_score, "ai_disambiguated" if ai_match else "ai_rejected"

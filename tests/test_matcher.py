import unittest
import asyncio
from unittest.mock import patch, AsyncMock
from src.resolver.matcher import EntityMatcher

class TestEntityMatcher(unittest.TestCase):
    def test_exact_match(self):
        match, score, match_type = asyncio.run(
            EntityMatcher.match_candidate(
                candidate_title="Solo Leveling",
                canonical_title="Solo Leveling",
                known_aliases=[]
            )
        )
        self.assertTrue(match)
        self.assertEqual(score, 100.0)
        self.assertEqual(match_type, "exact")

    def test_exact_alias_match(self):
        match, score, match_type = asyncio.run(
            EntityMatcher.match_candidate(
                candidate_title="I Alone Level Up",
                canonical_title="Solo Leveling",
                known_aliases=["I Alone Level Up", "Na Honjaman Lebel-eob"]
            )
        )
        self.assertTrue(match)
        self.assertEqual(score, 100.0)
        self.assertEqual(match_type, "exact_alias")

    def test_high_fuzzy_match(self):
        match, score, match_type = asyncio.run(
            EntityMatcher.match_candidate(
                candidate_title="Solo Leveling Season 2",
                canonical_title="Solo Leveling",
                known_aliases=[]
            )
        )
        self.assertTrue(match)
        self.assertGreaterEqual(score, 88.0)
        self.assertEqual(match_type, "rapidfuzz_high")

    def test_low_fuzzy_reject(self):
        match, score, match_type = asyncio.run(
            EntityMatcher.match_candidate(
                candidate_title="One Piece",
                canonical_title="Solo Leveling",
                known_aliases=[]
            )
        )
        self.assertFalse(match)
        self.assertLess(score, 60.0)
        self.assertEqual(match_type, "rapidfuzz_low")

    @patch("src.resolver.ai_disambiguator.AIDisambiguator.disambiguate", new_callable=AsyncMock)
    def test_gray_zone_ai_disambiguation(self, mock_ai):
        mock_ai.return_value = True
        match, score, match_type = asyncio.run(
            EntityMatcher.match_candidate(
                candidate_title="Only Leveling",
                canonical_title="Solo Leveling",
                known_aliases=[]
            )
        )
        self.assertTrue(match)
        self.assertEqual(match_type, "ai_disambiguated")
        mock_ai.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()

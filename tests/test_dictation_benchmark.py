"""Known edit counts and multilingual scoring rules for fair ASR comparisons."""

import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location(
    "dictation_benchmark", Path(__file__).parents[1] / "scripts/dictation-benchmark.py"
)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class ScoringTests(unittest.TestCase):
    def test_known_edits(self):
        result = benchmark.score("the quick brown fox jumps", "the slow fox jumps twice")
        self.assertEqual(result["substitutions"], 1)
        self.assertEqual(result["deletions"], 1)
        self.assertEqual(result["insertions"], 1)
        self.assertEqual(result["wer_percent"], 60)

    def test_danish_and_unicode(self):
        result = benchmark.score("Åse læser: RØD-GRØD!", "a\u030ase læser rød grød")
        self.assertEqual(result["wer_percent"], 0)

    def test_contractions_and_case(self):
        self.assertEqual(benchmark.score("Don’t use ddpm", "don't use DDPM")["wer_percent"], 0)
        self.assertEqual(benchmark.score("iMF", "IMF", case_sensitive=True)["wer_percent"], 100)

    def test_empty_hypothesis_and_large_wer(self):
        self.assertEqual(benchmark.score("one two", "")["deletions"], 2)
        self.assertEqual(benchmark.score("one", "one two three")["wer_percent"], 200)
        with self.assertRaises(ValueError):
            benchmark.score("...", "hello")

    def test_numbers_have_no_unstated_equivalence(self):
        self.assertEqual(benchmark.score("twenty", "20")["wer_percent"], 100)


if __name__ == "__main__":
    unittest.main()

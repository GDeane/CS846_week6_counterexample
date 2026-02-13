import unittest

from problem_A_1 import count_word_frequencies


class TestProblemA1(unittest.TestCase):
    def test_sample_paragraph(self):
        text = (
            "The quick brown fox jumps over the lazy dog. "
            "The dog was not lazy, but the fox was quick."
        )
        expected = {
            "the": 4,
            "quick": 2,
            "fox": 2,
            "lazy": 2,
            "dog": 2,
            "was": 2,
            "brown": 1,
            "jumps": 1,
            "over": 1,
            "not": 1,
            "but": 1,
        }
        self.assertEqual(count_word_frequencies(text), expected)

    def test_empty_string(self):
        self.assertEqual(count_word_frequencies(""), {})

    def test_punctuation_and_case(self):
        text = "Hello, hello! HELLO?"
        expected = {"hello": 3}
        self.assertEqual(count_word_frequencies(text), expected)

    def test_apostrophes(self):
        text = "Don't stop believing. Don't!"
        expected = {"don't": 2, "stop": 1, "believing": 1}
        self.assertEqual(count_word_frequencies(text), expected)

    def test_whitespace_variations(self):
        text = " spaced   words \nnew line "
        expected = {"spaced": 1, "words": 1, "new": 1, "line": 1}
        self.assertEqual(count_word_frequencies(text), expected)


if __name__ == "__main__":
    unittest.main()

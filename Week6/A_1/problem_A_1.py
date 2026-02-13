"""
Problem A_1: Count how many times each word appears in a paragraph.

Implement count_word_frequencies(text) so that it returns a dictionary
mapping each lowercase word to the number of occurrences. The intended
behavior follows the sample in the assignment:
- Case-insensitive: "The" and "the" both count toward "the".
- Ignore punctuation attached to words (commas, periods, etc.).
- Words are sequences of letters and apostrophes (e.g., "don't" counts as one word).

"""
from typing import Dict


def count_word_frequencies(text: str) -> Dict[str, int]:
    """Return a dict of lowercase words -> counts for the given text.

    Replace the body with your implementation. The current placeholder raises
    NotImplementedError so tests will fail until you implement it.
    """
    raise NotImplementedError("Implement this function to count word frequencies")


if __name__ == "__main__":
    # Simple manual run example
    sample = "The quick brown fox jumps over the lazy dog. The dog was not lazy, but the fox was quick."
    print(count_word_frequencies(sample))

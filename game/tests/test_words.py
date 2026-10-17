"""
Tests for the word list:
- words from adult, dating, gambling and drug sites stay out of WORD_LIST
- no board, across many deals, ever shows one of them
"""

from django.test import SimpleTestCase

from game.words import WORD_LIST, get_random_board


# Taken out of the web word-frequency list. Anyone can try the demo,
# so the board should never put these side by side.
BLOCKED_WORDS = (
    "sexual", "naked", "lesbian", "gay", "breast", "adult", "adults",
    "mature", "amateur", "oral", "teen", "teens", "girls", "dating",
    "casino", "poker", "drug", "drugs", "abuse", "kundan",
)


class BlockedWordTests(SimpleTestCase):
    def test_blocked_words_are_not_in_the_list(self):
        words = {w.lower() for w in WORD_LIST}
        for word in BLOCKED_WORDS:
            with self.subTest(word=word):
                self.assertNotIn(word, words)

    def test_boards_never_show_a_blocked_word(self):
        blocked = set(BLOCKED_WORDS)
        for _ in range(500):
            shown = {w['word'].lower() for w in get_random_board()}
            self.assertFalse(shown & blocked, f"board showed {shown & blocked}")

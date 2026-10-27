"""Game names: what a player is called in rooms, on the leaderboard, and by friends.

Names are unique and stay the player's key everywhere (ROADMAP, Phase 1), so they're kept
simple: 1-10 letters or digits, the first one a capital, as the home page's inputs type them.
"""

import secrets

from django.contrib.auth.models import User

from game.game_manager import BOT_NAME

MAX_LENGTH = 10


def tidy(raw):
    """A typed name as the game stores it: 'alice' and 'ALICE' are both 'Alice'."""
    return raw.strip().capitalize()


def problem_with(name):
    """Why `name` can't be a new player's name, or None if it can."""
    if not name or len(name) > MAX_LENGTH or not (name.isascii() and name.isalnum()):
        return f'Use 1-{MAX_LENGTH} letters or digits'
    if name == BOT_NAME or User.objects.filter(username__iexact=name).exists():
        return 'That name is taken'
    return None


def suggest(full_name):
    """A free name to offer someone new from Google: their first name, made to fit."""
    first = full_name.split(' ')[0] if full_name else ''
    base = ''.join(c for c in first if c.isascii() and c.isalnum())[:MAX_LENGTH].capitalize() or 'Player'
    if problem_with(base) is None:
        return base
    for _ in range(20):
        digits = str(secrets.randbelow(1000))
        candidate = base[:MAX_LENGTH - len(digits)] + digits
        if problem_with(candidate) is None:
            return candidate
    return ''

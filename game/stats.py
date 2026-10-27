"""Numbers about a player that more than one page shows."""

from django.contrib.auth.models import User
from django.db.models import Q


def global_rank(user):
    """Place on the global leaderboard: most earned seconds first, earlier sign-up first on a tie.

    Demo guests aren't on the board.
    """
    seconds = user.profile.total_earned_seconds
    return User.objects.exclude(profile__is_guest=True).filter(
        Q(profile__total_earned_seconds__gt=seconds) |
        Q(profile__total_earned_seconds=seconds, id__lt=user.id)
    ).count() + 1

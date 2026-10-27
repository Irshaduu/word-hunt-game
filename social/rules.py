"""The rules for friends and blocks, in one place, so pages and sockets agree.

Requests, friendships and blocks live in Postgres: people own them. Who is online doesn't
(presence.py keeps it in memory).
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.db.models import Q

from .models import Block, FriendRequest, Friendship

REQUESTS_PER_DAY = 20  # per player, so nobody can send one to the whole leaderboard

# What send_request did, for the page to say.
SENT = 'sent'
NOW_FRIENDS = 'now_friends'          # they had already asked you
ALREADY_SENT = 'already_sent'
ALREADY_FRIENDS = 'already_friends'
NOT_ALLOWED = 'not_allowed'          # yourself, a demo guest, or a block either way
TOO_MANY = 'too_many'


def _pair(a, b):
    return (a, b) if a.id < b.id else (b, a)


def are_friends(a, b):
    user_a, user_b = _pair(a, b)
    return Friendship.objects.filter(user_a=user_a, user_b=user_b).exists()


def blocked_between(a, b):
    """True if either has blocked the other. Which one did is never shown."""
    return Block.objects.filter(Q(blocker=a, blocked=b) | Q(blocker=b, blocked=a)).exists()


def friend_ids(user):
    pairs = Friendship.objects.filter(Q(user_a=user) | Q(user_b=user)).values_list('user_a_id', 'user_b_id')
    return {b if a == user.id else a for a, b in pairs}


def friends_of(user):
    return User.objects.filter(id__in=friend_ids(user)).select_related('profile').order_by('username')


def _make_friends(a, b):
    user_a, user_b = _pair(a, b)
    Friendship.objects.get_or_create(user_a=user_a, user_b=user_b)


def send_request(from_user, to_user):
    """Ask to_user to be friends. If they had already asked from_user, that counts as a yes."""
    if (from_user == to_user or from_user.profile.is_guest or to_user.profile.is_guest
            or blocked_between(from_user, to_user)):
        return NOT_ALLOWED
    if are_friends(from_user, to_user):
        return ALREADY_FRIENDS
    key = f'friend-requests:{from_user.id}'
    with transaction.atomic():
        crossing = FriendRequest.objects.filter(from_user=to_user, to_user=from_user)
        if crossing.exists():
            crossing.delete()
            _make_friends(from_user, to_user)
            return NOW_FRIENDS
        if FriendRequest.objects.filter(from_user=from_user, to_user=to_user).exists():
            return ALREADY_SENT
        sent_today = cache.get(key, 0)
        if sent_today >= REQUESTS_PER_DAY:
            return TOO_MANY
        FriendRequest.objects.create(from_user=from_user, to_user=to_user)
    cache.set(key, sent_today + 1, 60 * 60 * 24)
    return SENT


def accept(user, from_user):
    """user says yes to from_user's request. False if there was no such request."""
    with transaction.atomic():
        deleted, _ = FriendRequest.objects.filter(from_user=from_user, to_user=user).delete()
        if not deleted:
            return False
        _make_friends(user, from_user)
    return True


def decline(user, from_user):
    return FriendRequest.objects.filter(from_user=from_user, to_user=user).delete()[0] > 0


def cancel(user, to_user):
    return FriendRequest.objects.filter(from_user=user, to_user=to_user).delete()[0] > 0


def unfriend(user, other):
    user_a, user_b = _pair(user, other)
    return Friendship.objects.filter(user_a=user_a, user_b=user_b).delete()[0] > 0


def block(user, other):
    """user blocks other. Their friendship and any requests between them go too."""
    if user == other:
        return False
    with transaction.atomic():
        Block.objects.get_or_create(blocker=user, blocked=other)
        unfriend(user, other)
        FriendRequest.objects.filter(Q(from_user=user, to_user=other) | Q(from_user=other, to_user=user)).delete()
    return True


def unblock(user, other):
    return Block.objects.filter(blocker=user, blocked=other).delete()[0] > 0


def relationship(viewer, other):
    """Where viewer stands with other, for the buttons on other's profile."""
    if Block.objects.filter(blocker=viewer, blocked=other).exists():
        return 'blocked'
    if are_friends(viewer, other):
        return 'friends'
    if FriendRequest.objects.filter(from_user=viewer, to_user=other).exists():
        return 'sent'
    if FriendRequest.objects.filter(from_user=other, to_user=viewer).exists():
        return 'received'
    return 'none'

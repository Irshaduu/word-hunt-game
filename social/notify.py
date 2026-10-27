"""Messages from ordinary (sync) views to a player's open pages, over their /ws/me/ sockets."""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from .presence import group


def tell(user, message):
    """Send `message` (a dict with a 'type') to every open page of `user`."""
    async_to_sync(get_channel_layer().group_send)(group(user.id), message)


def friends_changed(*users):
    """Their friends lists changed: each open page reloads it."""
    for user in users:
        tell(user, {'type': 'friends_changed'})

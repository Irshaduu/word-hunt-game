"""The app-wide socket, /ws/me/: one per open page of a signed-in player.

It carries friends' online status and friend requests, and invites and random matches too
(Phase 4). What it knows about who is online lives in presence.py.
"""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from game.consumers import turn_away
from . import presence
from .models import FriendRequest
from .rules import friends_of


@database_sync_to_async
def friends_and_requests(user):
    friends = [(f.id, f.username) for f in friends_of(user)]
    return friends, FriendRequest.objects.filter(to_user=user).count()


class MeConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        if not user.is_authenticated:
            await turn_away(self)
            return
        self.user = user
        await self.channel_layer.group_add(presence.group(user.id), self.channel_name)
        await self.accept()
        await self.send_friends()
        await presence.connected(user.id)

    async def disconnect(self, code):
        if not hasattr(self, 'user'):
            return  # turned away
        await self.channel_layer.group_discard(presence.group(self.user.id), self.channel_name)
        await presence.disconnected(self.user.id)

    async def send_friends(self):
        """Their friends and how each is doing, and how many friend requests wait for them."""
        friends, requests = await friends_and_requests(self.user)
        presence.set_friends(self.user.id, self.user.username, [i for i, _ in friends])
        await self.send_json({
            'type': 'friends',
            'friends': [{'name': name, 'status': presence.status(i)} for i, name in friends],
            'requests': requests,
        })

    # Messages for this player, from presence.py and social/notify.py

    async def friend_status(self, event):
        await self.send_json({'type': 'friend_status', 'name': event['name'], 'status': event['status']})

    async def friend_request(self, event):
        await self.send_json({'type': 'friend_request', 'from': event['from']})

    async def friends_changed(self, event):
        await self.send_friends()

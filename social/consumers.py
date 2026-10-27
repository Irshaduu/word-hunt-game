"""The app-wide socket, /ws/me/: one per open page of a signed-in player.

It carries friends' online status, friend requests and game invites, and it is how a page
waits in the random-match queue (game/matchmaking.py). What it knows about who is online
lives in presence.py.
"""

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from game import matchmaking
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
        self.invited_by = {}  # name -> user id of everyone whose invite reached this page
        await self.channel_layer.group_add(presence.group(user.id), self.channel_name)
        await self.accept()
        await self.send_friends()
        await presence.connected(user.id)

    async def disconnect(self, code):
        if not hasattr(self, 'user'):
            return  # turned away
        matchmaking.leave(self.user.id, self.channel_name)  # a waiting page that closes stops waiting
        await self.channel_layer.group_discard(presence.group(self.user.id), self.channel_name)
        await presence.disconnected(self.user.id)

    async def receive_json(self, content):
        kind = content.get('type')
        if kind == 'queue_join':
            await self.send_json({'type': 'queue_joined'})
            await matchmaking.join(self.user.id, self.user.username, self.channel_name)
        elif kind == 'queue_leave':
            matchmaking.leave(self.user.id, self.channel_name)
        elif kind == 'decline_invite':
            # Only to someone whose invite reached this page, so nobody can be sent these at random.
            inviter_id = self.invited_by.pop(content.get('from'), None)
            if inviter_id is not None:
                await self.channel_layer.group_send(presence.group(inviter_id), {
                    'type': 'invite_declined', 'by': self.user.username,
                })

    async def send_friends(self):
        """Their friends and how each is doing, and how many friend requests wait for them."""
        friends, requests = await friends_and_requests(self.user)
        presence.set_friends(self.user.id, self.user.username, [i for i, _ in friends])
        await self.send_json({
            'type': 'friends',
            'friends': [{'name': name, 'status': presence.status(i)} for i, name in friends],
            'requests': requests,
        })

    # Messages for this player, from presence.py, social/notify.py and game/matchmaking.py

    async def friend_status(self, event):
        await self.send_json({'type': 'friend_status', 'name': event['name'], 'status': event['status']})

    async def friend_request(self, event):
        await self.send_json({'type': 'friend_request', 'from': event['from']})

    async def friends_changed(self, event):
        await self.send_friends()

    async def invite(self, event):
        self.invited_by[event['from']] = event['from_id']
        await self.send_json({'type': 'invite', 'from': event['from'], 'room': event['room']})

    async def invite_declined(self, event):
        await self.send_json({'type': 'invite_declined', 'by': event['by']})

    async def match_found(self, event):
        await self.send_json({'type': 'match_found', 'room': event['room']})

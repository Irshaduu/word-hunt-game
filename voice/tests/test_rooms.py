"""
Tests for voice rooms (voice/rooms.py and the room socket in voice/consumers.py):
- a room is named (or named after its owner), holds 8, and can be locked; the owner still gets in
- someone the owner removed can't come back; a newer page of a member replaces the older one
- an owner who left has a while to come back (a reload); then the room goes to whoever has been
  there longest, or closes if it's empty
- blocks are both ways: people blocked with each other don't see, hear or read each other
- the list shows busy rooms first, and clears rooms nobody ever entered
- over real sockets: everyone gets the room as they see it; chat reaches everyone but the blocked,
  one message a second; only the owner mutes, removes and locks, and a mute holds on a new page;
  demo guests, the full, the removed and people blocked with the owner are turned away
"""

import asyncio
import time
from unittest import mock

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TransactionTestCase

from social import rules
from voice import rooms
from wordhunt.asgi import application


class RoomRuleTests(SimpleTestCase):
    def setUp(self):
        rooms.ROOMS.clear()

    def tearDown(self):
        rooms.ROOMS.clear()

    def test_a_room_is_named_or_named_after_its_owner(self):
        self.assertEqual(rooms.create('  Late night words  ', 'Asha').name, 'Late night words')
        self.assertEqual(rooms.create('', 'Asha').name, "Asha's room")
        self.assertEqual(len(rooms.create('x' * 99, 'Asha').name), rooms.NAME_LENGTH)

    def test_eight_fit_a_ninth_does_not(self):
        room = rooms.create('Full', 'P0')
        for i in range(rooms.MAX_MEMBERS):
            room.join(f'P{i}', f'chan-{i}', set())
        self.assertEqual(room.problem_joining('P9'), 'full')
        self.assertIsNone(room.problem_joining('P3'))  # another page of someone inside

    def test_a_locked_room_still_lets_its_owner_in(self):
        room = rooms.create('Ours', 'Asha')
        room.locked = True
        self.assertEqual(room.problem_joining('Ben'), 'locked')
        self.assertIsNone(room.problem_joining('Asha'))

    def test_someone_removed_cannot_come_back(self):
        room = rooms.create('Ours', 'Asha')
        room.removed.add('Ben')
        self.assertEqual(room.problem_joining('Ben'), 'removed')

    def test_a_newer_page_replaces_the_older_one(self):
        room = rooms.create('Ours', 'Asha')
        room.join('Asha', 'old-page', set())
        room.join('Asha', 'new-page', set())
        self.assertFalse(room.leave('Asha', 'old-page'))
        self.assertIn('Asha', room.members)
        self.assertTrue(room.leave('Asha', 'new-page'))

    def test_an_owner_away_too_long_hands_the_room_on(self):
        room = rooms.create('Ours', 'Asha')
        room.join('Asha', 'a', set())
        room.join('Ben', 'b', set())
        room.members['Ben'].joined_at -= 10  # (as if Ben had been there longer)
        room.join('Cara', 'c', set())
        room.leave('Asha', 'a')
        first = room.owner_absences
        room.join('Asha', 'a2', set())  # a reload
        self.assertFalse(room.owner_gone(first))
        room.leave('Asha', 'a2')
        self.assertFalse(room.owner_gone(first))  # that absence ended; this one has its own wait
        self.assertTrue(room.owner_gone(room.owner_absences))
        self.assertEqual(room.owner, 'Ben')

    def test_a_room_left_empty_closes_when_its_owner_is_gone(self):
        room = rooms.create('Ours', 'Asha')
        room.join('Asha', 'a', set())
        room.leave('Asha', 'a')
        self.assertIn(room.id, rooms.ROOMS)  # still there for a reload
        room.owner_gone(room.owner_absences)
        self.assertNotIn(room.id, rooms.ROOMS)

    def test_blocks_are_both_ways(self):
        room = rooms.create('Ours', 'Asha')
        room.join('Asha', 'a', set())
        room.join('Ben', 'b', {'Asha'})
        self.assertFalse(room.can_hear('Asha', 'Ben'))
        self.assertFalse(room.can_hear('Ben', 'Asha'))
        room.join('Cara', 'c', set())
        room.block('Cara', 'Asha')
        self.assertFalse(room.can_hear('Asha', 'Cara'))
        self.assertTrue(room.can_hear('Ben', 'Cara'))

    def test_the_list_shows_busy_rooms_first_and_clears_unentered_ones(self):
        quiet = rooms.create('Quiet', 'Asha')
        quiet.join('Asha', 'a', set())
        busy = rooms.create('Busy', 'Ben')
        busy.join('Ben', 'b', set())
        busy.join('Cara', 'c', set())
        never = rooms.create('Never entered', 'Dev')
        never.created_at -= rooms.EMPTY_ROOM_SECONDS + 1
        self.assertEqual([r.name for r in rooms.listing()], ['Busy', 'Quiet'])
        self.assertNotIn(never.id, rooms.ROOMS)


class RoomSocketTests(TransactionTestCase):
    def setUp(self):
        rooms.ROOMS.clear()
        self.users, self.sessions = {}, {}
        for name in ['Asha', 'Ben', 'Cara'] + [f'P{i}' for i in range(rooms.MAX_MEMBERS)]:
            self.users[name] = User.objects.create_user(username=name)
            client = Client()
            client.force_login(self.users[name])
            self.sessions[name] = client.cookies['sessionid'].value
        self.room = rooms.create('Words at night', 'Asha')

    def tearDown(self):
        rooms.ROOMS.clear()

    def socket(self, name):
        return WebsocketCommunicator(application, f'/ws/rooms/{self.room.id}/', headers=[
            (b'origin', b'http://testserver'), (b'cookie', f'sessionid={self.sessions[name]}'.encode())])

    async def enter(self, name):
        """Keep what this returns: a dropped socket is collected mid-connect."""
        ws = self.socket(name)
        connected, _ = await ws.connect()
        self.assertTrue(connected)
        return ws

    async def latest(self, ws):
        """The last message waiting on this socket."""
        message = await ws.receive_json_from()
        while not await ws.receive_nothing(timeout=0.1):
            message = await ws.receive_json_from()
        return message

    async def turned_away(self, ws):
        await ws.connect()
        message = await ws.receive_output()
        return (message['type'], message.get('code')) == ('websocket.close', 4004)

    async def test_everyone_gets_the_room_as_they_see_it(self):
        asha = await self.enter('Asha')
        ben = await self.enter('Ben')
        state = await self.latest(asha)
        self.assertEqual((state['type'], state['name'], state['owner']), ('room', 'Words at night', 'Asha'))
        self.assertEqual([m['name'] for m in state['members']], ['Asha', 'Ben'])
        self.assertEqual([m['name'] for m in (await self.latest(ben))['members']], ['Asha', 'Ben'])
        await ben.disconnect()
        await asha.disconnect()

    async def test_chat_reaches_everyone_but_the_blocked_once_a_second(self):
        await database_sync_to_async(rules.block)(self.users['Ben'], self.users['Cara'])
        asha, ben, cara = await self.enter('Asha'), await self.enter('Ben'), await self.enter('Cara')
        for ws in (asha, ben, cara):
            await self.latest(ws)
        await ben.send_json_to({'type': 'chat', 'text': '  hello  '})
        self.assertEqual(await asha.receive_json_from(), {'type': 'chat', 'from': 'Ben', 'text': 'hello'})
        self.assertEqual(await ben.receive_json_from(), {'type': 'chat', 'from': 'Ben', 'text': 'hello'})
        self.assertTrue(await cara.receive_nothing(timeout=0.1))  # blocked with Ben
        await ben.send_json_to({'type': 'chat', 'text': 'again, too soon'})
        self.assertTrue(await asha.receive_nothing(timeout=0.1))
        for ws in (asha, ben, cara):
            await ws.disconnect()

    async def test_only_the_owner_mutes_removes_and_locks(self):
        asha, ben = await self.enter('Asha'), await self.enter('Ben')
        await self.latest(asha)
        await self.latest(ben)
        await ben.send_json_to({'type': 'lock', 'locked': True})  # not the owner: nothing happens
        self.assertTrue(await asha.receive_nothing(timeout=0.1))

        await asha.send_json_to({'type': 'mute', 'name': 'Ben', 'muted': True})
        ben_state = await self.latest(ben)
        self.assertTrue([m for m in ben_state['members'] if m['name'] == 'Ben'][0]['muted'])

        await asha.send_json_to({'type': 'lock', 'locked': True})
        self.assertTrue((await self.latest(asha))['locked'])
        await self.latest(ben)
        self.assertTrue(await self.turned_away(self.socket('Cara')))

        await asha.send_json_to({'type': 'remove', 'name': 'Ben'})
        self.assertEqual(await ben.receive_json_from(), {'type': 'removed'})
        self.assertEqual((await ben.receive_output())['code'], 4003)
        self.room.locked = False
        self.assertTrue(await self.turned_away(self.socket('Ben')))  # can't come back
        await asha.disconnect()

    async def test_a_mute_holds_on_a_new_page(self):
        asha, ben = await self.enter('Asha'), await self.enter('Ben')
        await self.latest(asha)
        await asha.send_json_to({'type': 'mute', 'name': 'Ben', 'muted': True})
        self.assertTrue([m for m in (await self.latest(ben))['members'] if m['name'] == 'Ben'][0]['muted'])
        await ben.disconnect()
        ben = await self.enter('Ben')  # reloading doesn't shake off the owner's mute
        self.assertTrue([m for m in (await self.latest(ben))['members'] if m['name'] == 'Ben'][0]['muted'])
        await ben.disconnect()
        await asha.disconnect()

    async def test_the_full_guests_and_people_blocked_with_the_owner_are_turned_away(self):
        members = [await self.enter(f'P{i}') for i in range(rooms.MAX_MEMBERS)]
        self.assertTrue(await self.turned_away(self.socket('Cara')))  # full
        for ws in members:
            await ws.disconnect()

        await database_sync_to_async(rules.block)(self.users['Asha'], self.users['Ben'])
        self.assertTrue(await self.turned_away(self.socket('Ben')))

        guest = await User.objects.acreate(username='Guest0001')
        await type(guest.profile).objects.filter(user=guest).aupdate(is_guest=True)
        client = Client()
        await client.aforce_login(guest)
        self.sessions['Guest0001'] = client.cookies['sessionid'].value
        self.assertTrue(await self.turned_away(self.socket('Guest0001')))

    async def test_the_owner_has_a_while_to_come_back(self):
        with mock.patch.object(rooms, 'OWNER_AWAY_SECONDS', 0.3):
            asha, ben = await self.enter('Asha'), await self.enter('Ben')
            await self.latest(ben)
            await asha.disconnect()
            asha = await self.enter('Asha')  # a reload
            await asyncio.sleep(0.5)
            self.assertEqual((await self.latest(ben))['owner'], 'Asha')

            await asha.disconnect()  # gone for good
            await asyncio.sleep(0.5)
            self.assertEqual((await self.latest(ben))['owner'], 'Ben')

            await ben.disconnect()  # the last one out
            self.assertIn(self.room.id, rooms.ROOMS)
            await asyncio.sleep(0.5)
            self.assertNotIn(self.room.id, rooms.ROOMS)

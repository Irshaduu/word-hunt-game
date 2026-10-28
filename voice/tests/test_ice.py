"""
Tests for ICE servers (voice/ice.py and /voice/ice/):
- without Cloudflare keys, STUN only, and Cloudflare is never called
- with keys, Cloudflare is asked once an hour, with the token, and port 53 addresses are dropped
- if Cloudflare fails, STUN only (for a minute), and it's logged
- TURN goes only to players in a room with voice; everyone else gets STUN
"""

import json
from unittest import mock

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from game.game_manager import ROOMS, GameRoom
from voice import ice

KEYS = {'CLOUDFLARE_TURN_KEY_ID': 'key-1', 'CLOUDFLARE_TURN_API_TOKEN': 'secret-token'}

CLOUDFLARE_ANSWER = {'iceServers': [
    {'urls': ['stun:stun.cloudflare.com:3478', 'stun:stun.cloudflare.com:53']},
    {'urls': ['turn:turn.cloudflare.com:3478?transport=udp', 'turn:turn.cloudflare.com:53?transport=udp',
              'turns:turn.cloudflare.com:443?transport=tcp'],
     'username': 'short-lived-user', 'credential': 'short-lived-password'},
]}


class Answer:
    """What urlopen hands back: a response to read and close."""

    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def read(self, *args):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class IceServerTests(SimpleTestCase):
    def setUp(self):
        ice.forget()

    def tearDown(self):
        ice.forget()

    @override_settings(CLOUDFLARE_TURN_KEY_ID='', CLOUDFLARE_TURN_API_TOKEN='')
    def test_without_keys_stun_only(self):
        with mock.patch('voice.ice.urllib.request.urlopen') as urlopen:
            self.assertEqual(ice.ice_servers(), ice.STUN)
        urlopen.assert_not_called()

    @override_settings(**KEYS)
    def test_with_keys_cloudflare_is_asked_once_an_hour(self):
        with mock.patch('voice.ice.urllib.request.urlopen', return_value=Answer(CLOUDFLARE_ANSWER)) as urlopen:
            servers = ice.ice_servers()
            self.assertEqual(ice.ice_servers(), servers)  # cached
        self.assertEqual(urlopen.call_count, 1)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url,
                         'https://rtc.live.cloudflare.com/v1/turn/keys/key-1/credentials/generate-ice-servers')
        self.assertEqual(request.get_header('Authorization'), 'Bearer secret-token')
        self.assertEqual(json.loads(request.data), {'ttl': ice.TTL_SECONDS})
        self.assertEqual(servers[-1]['username'], 'short-lived-user')
        urls = [url for server in servers for url in server['urls']]
        self.assertIn('turns:turn.cloudflare.com:443?transport=tcp', urls)
        self.assertFalse([url for url in urls if ':53' in url])

    @override_settings(**KEYS)
    def test_when_cloudflare_fails_stun_only_and_it_is_logged(self):
        with mock.patch('voice.ice.urllib.request.urlopen', side_effect=OSError('Cloudflare is down')):
            with self.assertLogs('voice.ice', level='ERROR'):
                self.assertEqual(ice.ice_servers(), ice.STUN)


@override_settings(**KEYS)
class IceViewTests(TestCase):
    def setUp(self):
        ROOMS.clear()
        self.asha = User.objects.create_user(username='Asha')
        self.client.force_login(self.asha)
        turn = {'urls': ['turns:turn.cloudflare.com:443?transport=tcp'], 'username': 'u', 'credential': 'c'}
        ice._cache.update(servers=ice.STUN + [turn], until=float('inf'))  # as if Cloudflare had answered

    def tearDown(self):
        ice.forget()
        ROOMS.clear()

    def test_a_player_in_a_room_with_voice_gets_turn(self):
        room = GameRoom('VOX', creator='Asha')
        room.add_player('Asha')
        ROOMS['VOX'] = room
        servers = self.client.get(reverse('voice_ice'), {'room': 'vox'}).json()['iceServers']
        self.assertTrue(any('credential' in server for server in servers))

    def test_everyone_else_gets_stun_only(self):
        ROOMS['VOX'] = GameRoom('VOX', creator='Ben')  # Asha isn't in it
        self.assertEqual(self.client.get(reverse('voice_ice'), {'room': 'VOX'}).json()['iceServers'], ice.STUN)
        match = GameRoom('RND', creator='Asha', matchmade=True)  # strangers: no voice
        match.add_player('Asha')
        ROOMS['RND'] = match
        self.assertEqual(self.client.get(reverse('voice_ice'), {'room': 'RND'}).json()['iceServers'], ice.STUN)

    def test_it_needs_signing_in(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('voice_ice')).status_code, 302)

"""
Tests for the voice rooms' SFU side (voice/sfu.py and its endpoints in voice/views.py),
with Cloudflare stood in for:
- publish makes a session, then publishes the browser's microphone as one local track
- pull asks for others' tracks by session and track name; renegotiate sends the answer
- Cloudflare errors, per request or per track, become SFUError
- the endpoints: rooms page and opening a room; a room needs Cloudflare keys for voice;
  publish keeps the player's session and track and tells the room; pull only brings in people
  the player may hear, and says whose each track is; stop takes them off; report is kept and
  limited; block blocks and updates the room; people not in the room get 404
"""

import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from social import rules
from voice import rooms, sfu
from voice.models import Report

KEYS = {'CLOUDFLARE_SFU_APP_ID': 'app-1', 'CLOUDFLARE_SFU_APP_SECRET': 'app-secret'}
OFFER = {'type': 'offer', 'sdp': 'v=0 offer'}
ANSWER = {'type': 'answer', 'sdp': 'v=0 answer'}


class Answer:
    def __init__(self, body):
        self.body = json.dumps(body).encode()

    def read(self, *args):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@override_settings(**KEYS)
class SFUClientTests(SimpleTestCase):
    def test_publish_makes_a_session_then_publishes_the_microphone(self):
        replies = [Answer({'sessionId': 'sess-1'}), Answer({'sessionDescription': ANSWER, 'tracks': [{'mid': '0', 'trackName': 't-1'}]})]
        with mock.patch('voice.sfu.urllib.request.urlopen', side_effect=replies) as urlopen:
            self.assertEqual(sfu.publish(OFFER, '0', 't-1'), ('sess-1', ANSWER))
        new, tracks = (call.args[0] for call in urlopen.call_args_list)
        self.assertEqual((new.get_method(), new.full_url), ('POST', 'https://rtc.live.cloudflare.com/v1/apps/app-1/sessions/new'))
        self.assertEqual(new.get_header('Authorization'), 'Bearer app-secret')
        self.assertEqual(tracks.full_url, 'https://rtc.live.cloudflare.com/v1/apps/app-1/sessions/sess-1/tracks/new')
        self.assertEqual(json.loads(tracks.data), {
            'sessionDescription': OFFER,
            'tracks': [{'location': 'local', 'mid': '0', 'trackName': 't-1'}],
        })

    def test_pull_and_renegotiate(self):
        reply = {'requiresImmediateRenegotiation': True, 'sessionDescription': OFFER,
                 'tracks': [{'mid': '1', 'trackName': 't-2', 'sessionId': 'sess-2'}]}
        with mock.patch('voice.sfu.urllib.request.urlopen', return_value=Answer(reply)) as urlopen:
            self.assertEqual(sfu.pull('sess-1', [('sess-2', 't-2')]), reply)
        self.assertEqual(json.loads(urlopen.call_args.args[0].data),
                         {'tracks': [{'location': 'remote', 'sessionId': 'sess-2', 'trackName': 't-2'}]})
        with mock.patch('voice.sfu.urllib.request.urlopen', return_value=Answer({})) as urlopen:
            sfu.renegotiate('sess-1', ANSWER)
        request = urlopen.call_args.args[0]
        self.assertEqual((request.get_method(), request.full_url),
                         ('PUT', 'https://rtc.live.cloudflare.com/v1/apps/app-1/sessions/sess-1/renegotiate'))
        self.assertEqual(json.loads(request.data), {'sessionDescription': ANSWER})

    def test_cloudflare_errors_become_sfu_errors(self):
        with mock.patch('voice.sfu.urllib.request.urlopen', return_value=Answer({'errorCode': 'bad_session'})):
            with self.assertRaises(sfu.SFUError):
                sfu.renegotiate('sess-1', ANSWER)
        failing_track = {'tracks': [{'trackName': 't-2', 'errorCode': 'not_found'}]}
        with mock.patch('voice.sfu.urllib.request.urlopen', return_value=Answer(failing_track)):
            with self.assertRaises(sfu.SFUError):
                sfu.pull('sess-1', [('sess-2', 't-2')])
        with mock.patch('voice.sfu.urllib.request.urlopen', side_effect=OSError('down')):
            with self.assertRaises(sfu.SFUError):
                sfu.renegotiate('sess-1', ANSWER)

    @override_settings(CLOUDFLARE_SFU_APP_ID='', CLOUDFLARE_SFU_APP_SECRET='')
    def test_not_configured_without_keys(self):
        self.assertFalse(sfu.configured())


class RoomPageTests(TestCase):
    def setUp(self):
        cache.clear()
        rooms.ROOMS.clear()
        self.asha = User.objects.create_user(username='Asha')
        self.ben = User.objects.create_user(username='Ben')
        self.cara = User.objects.create_user(username='Cara')
        self.client.force_login(self.asha)
        self.room = rooms.create('Words at night', 'Asha')
        for name in ('Asha', 'Ben', 'Cara'):
            self.room.join(name, f'channel-of-{name}', set())

    def tearDown(self):
        rooms.ROOMS.clear()

    def url(self, name, *args):
        return reverse(name, args=[self.room.id, *args])

    def post_json(self, name, body=None):
        return self.client.post(self.url(name), json.dumps(body or {}), content_type='application/json')

    def test_the_rooms_page_lists_rooms_and_opens_new_ones(self):
        self.assertContains(self.client.get(reverse('voice_rooms')), 'Words at night')
        response = self.client.post(reverse('voice_rooms'), {'name': 'Second room'})
        new = [r for r in rooms.ROOMS.values() if r.name == 'Second room'][0]
        self.assertRedirects(response, reverse('voice_room', args=[new.id]))
        self.assertEqual(new.owner, 'Asha')

    def test_opening_rooms_is_limited(self):
        for i in range(5):
            self.client.post(reverse('voice_rooms'), {'name': f'Room {i}'})
        response = self.client.post(reverse('voice_rooms'), {'name': 'One more'})
        self.assertContains(response, 'a lot of rooms')

    @override_settings(CLOUDFLARE_SFU_APP_ID='', CLOUDFLARE_SFU_APP_SECRET='')
    def test_voice_needs_cloudflare_keys(self):
        self.assertContains(self.client.get(self.url('voice_room')), "Voice in rooms isn't switched on yet")
        self.assertEqual(self.post_json('sfu_publish', {'sessionDescription': OFFER, 'mid': '0'}).status_code, 503)

    @override_settings(**KEYS)
    def test_publish_keeps_the_session_and_track_and_tells_the_room(self):
        with mock.patch('voice.views.sfu.publish', return_value=('sess-a', ANSWER)) as publish, \
                mock.patch('voice.views._tell_room') as tell_room:
            response = self.post_json('sfu_publish', {'sessionDescription': OFFER, 'mid': '0'})
        self.assertEqual(response.json(), {'sessionDescription': ANSWER})
        asha = self.room.members['Asha']
        self.assertEqual(asha.session, 'sess-a')
        self.assertTrue(asha.track.startswith(self.room.id))
        self.assertEqual(publish.call_args.args[:2], (OFFER, '0'))
        tell_room.assert_called_once_with(self.room)

    @override_settings(**KEYS)
    def test_pull_brings_in_only_people_one_may_hear(self):
        members = self.room.members
        members['Asha'].session = 'sess-a'
        members['Ben'].session, members['Ben'].track = 'sess-b', 'track-b'
        members['Cara'].session, members['Cara'].track = 'sess-c', 'track-c'
        self.room.block('Asha', 'Cara')
        reply = {'requiresImmediateRenegotiation': True, 'sessionDescription': OFFER,
                 'tracks': [{'mid': '1', 'trackName': 'track-b', 'sessionId': 'sess-b'}]}
        with mock.patch('voice.views.sfu.pull', return_value=reply) as pull:
            response = self.post_json('sfu_pull', {'names': ['Ben', 'Cara', 'Nobody']})
        pull.assert_called_once_with('sess-a', [('sess-b', 'track-b')])
        self.assertEqual(response.json()['tracks'], [{'mid': '1', 'name': 'Ben'}])
        self.assertTrue(response.json()['requiresImmediateRenegotiation'])

    @override_settings(**KEYS)
    def test_renegotiate_and_stop(self):
        self.room.members['Asha'].session, self.room.members['Asha'].track = 'sess-a', 'track-a'
        with mock.patch('voice.views.sfu.renegotiate') as renegotiate:
            self.assertEqual(self.post_json('sfu_renegotiate', {'sessionDescription': ANSWER}).json(), {'ok': True})
        renegotiate.assert_called_once_with('sess-a', ANSWER)
        with mock.patch('voice.views._tell_room'):
            self.post_json('sfu_stop')
        self.assertIsNone(self.room.members['Asha'].track)

    def test_a_report_is_kept_and_limited(self):
        response = self.client.post(self.url('room_report', 'Ben'), {'reason': 'shouting'})
        self.assertTrue(response.json()['ok'])
        report = Report.objects.get()
        self.assertEqual((report.reporter, report.reported, report.room_name, report.reason),
                         (self.asha, self.ben, 'Words at night', 'shouting'))
        for _ in range(4):
            self.client.post(self.url('room_report', 'Ben'))
        self.assertEqual(self.client.post(self.url('room_report', 'Ben')).status_code, 429)
        self.assertEqual(Report.objects.count(), 5)

    def test_block_blocks_and_updates_the_room(self):
        with mock.patch('voice.views._tell_room'):
            self.assertTrue(self.client.post(self.url('room_block', 'Ben')).json()['ok'])
        self.assertTrue(rules.blocked_between(self.asha, self.ben))
        self.assertFalse(self.room.can_hear('Asha', 'Ben'))
        self.assertFalse(self.room.can_hear('Ben', 'Asha'))

    def test_people_not_in_the_room_get_nothing(self):
        self.room.leave('Asha', 'channel-of-Asha')
        self.assertEqual(self.post_json('sfu_pull', {'names': ['Ben']}).status_code, 404)
        self.assertEqual(self.client.post(self.url('room_report', 'Ben')).status_code, 404)

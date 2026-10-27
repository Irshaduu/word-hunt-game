"""
Tests for checking a Google credential (accounts/google.py), with a key made for the test:
- a token Google signed for this app gives its claims
- a token for another app, an expired one, one from another issuer, or a forged one is refused
- nothing is accepted while GOOGLE_CLIENT_ID is unset
- only pictures on Google's CDN are kept
"""

import time
from types import SimpleNamespace
from unittest import mock

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.test import SimpleTestCase, override_settings

from accounts import google

CLIENT_ID = 'test-client.apps.googleusercontent.com'
GOOGLES_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
SOMEONE_ELSES_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def credential(key=GOOGLES_KEY, **changes):
    now = int(time.time())
    claims = {
        'iss': 'https://accounts.google.com', 'aud': CLIENT_ID, 'sub': '1234567890',
        'iat': now, 'exp': now + 3600,
        'name': 'Asha Menon', 'given_name': 'Asha',
        'picture': 'https://lh3.googleusercontent.com/a/photo=s96-c',
    }
    claims.update(changes)
    return jwt.encode(claims, key, algorithm='RS256', headers={'kid': 'test-key'})


# Google's published keys, as the client would fetch them: here, just the test's key.
@mock.patch.object(google._keys, 'get_signing_key_from_jwt', lambda token: SimpleNamespace(key=GOOGLES_KEY.public_key()))
@override_settings(GOOGLE_CLIENT_ID=CLIENT_ID)
class VerifyTests(SimpleTestCase):
    def test_a_credential_google_signed_for_this_app_gives_its_claims(self):
        claims = google.verify(credential())
        self.assertEqual((claims['sub'], claims['given_name']), ('1234567890', 'Asha'))

    def test_a_credential_for_another_app_is_refused(self):
        with self.assertRaises(google.InvalidCredential):
            google.verify(credential(aud='another-app.apps.googleusercontent.com'))

    def test_an_expired_credential_is_refused(self):
        with self.assertRaises(google.InvalidCredential):
            google.verify(credential(exp=int(time.time()) - 3600))

    def test_a_credential_from_another_issuer_is_refused(self):
        with self.assertRaises(google.InvalidCredential):
            google.verify(credential(iss='https://accounts.example.com'))

    def test_a_forged_credential_is_refused(self):
        with self.assertRaises(google.InvalidCredential):
            google.verify(credential(key=SOMEONE_ELSES_KEY))

    def test_garbage_is_refused(self):
        with self.assertRaises(google.InvalidCredential):
            google.verify('not-a-credential')

    @override_settings(GOOGLE_CLIENT_ID='')
    def test_nothing_is_accepted_until_a_client_id_is_set(self):
        with self.assertRaises(google.InvalidCredential):
            google.verify(credential())


class PictureTests(SimpleTestCase):
    def test_pictures_on_googles_cdn_are_kept(self):
        url = 'https://lh3.googleusercontent.com/a/photo=s96-c'
        self.assertEqual(google.picture_url({'picture': url}), url)

    def test_anything_else_is_dropped(self):
        for url in ('http://lh3.googleusercontent.com/a/photo', 'https://example.com/photo.png',
                    'https://googleusercontent.com.example.com/photo', 'javascript:alert(1)', ''):
            self.assertEqual(google.picture_url({'picture': url}), '', url)

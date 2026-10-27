"""
Tests for signing in with Google (the credential check itself is in test_google.py and mocked here):
- a returning Google player is signed in, and their picture kept current
- someone new chooses a name and gets an account with no PIN
- a chosen name follows the same rules as a PIN sign-up, and one is suggested from Google
- a PIN player links Google from their profile; a guest who signs in with Google gets a new account
- a bad credential gets an error, not a sign-in
- the Google button shows only once GOOGLE_CLIENT_ID is set
"""

from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts import google
from game.models import PlayerProfile

PICTURE = 'https://lh3.googleusercontent.com/a/photo=s96-c'


def google_account(sub='g-1', given_name='Asha', picture=PICTURE):
    return {'sub': sub, 'given_name': given_name, 'name': f'{given_name} Menon', 'picture': picture}


@override_settings(GOOGLE_CLIENT_ID='test-client')
class GoogleSignInTests(TestCase):
    def sign_in(self, account):
        with mock.patch('accounts.google.verify', return_value=account):
            return self.client.post(reverse('google_sign_in'), {'credential': 'signed-by-google'})

    def signed_in_as(self):
        return User.objects.filter(id=self.client.session.get('_auth_user_id')).first()

    def test_a_returning_google_player_is_signed_in_with_their_picture_current(self):
        asha = User.objects.create_user(username='Asha')
        PlayerProfile.objects.filter(user=asha).update(google_sub='g-1', avatar_url='https://lh3.googleusercontent.com/old')
        response = self.sign_in(google_account())
        self.assertEqual(response.json(), {'next': reverse('landing')})
        self.assertEqual(self.signed_in_as(), asha)
        self.assertEqual(PlayerProfile.objects.get(user=asha).avatar_url, PICTURE)

    def test_someone_new_chooses_a_name_and_gets_an_account_with_no_pin(self):
        response = self.sign_in(google_account(sub='g-2', given_name='Ben'))
        self.assertEqual(response.json(), {'next': reverse('choose_name')})
        self.assertIsNone(self.signed_in_as())

        page = self.client.get(reverse('choose_name'))
        self.assertContains(page, 'value="Ben"')  # suggested from their Google name

        response = self.client.post(reverse('choose_name'), {'username': 'ben'})
        self.assertRedirects(response, reverse('landing'))
        ben = User.objects.get(username='Ben')
        self.assertEqual(self.signed_in_as(), ben)
        self.assertFalse(ben.has_usable_password())
        self.assertEqual((ben.profile.google_sub, ben.profile.avatar_url), ('g-2', PICTURE))

    def test_a_chosen_name_follows_the_pin_sign_up_rules(self):
        User.objects.create_user(username='Ben', password='1234')
        self.sign_in(google_account(sub='g-2', given_name='Ben'))
        suggestion = self.client.get(reverse('choose_name')).context['name']
        self.assertTrue(suggestion.startswith('Ben') and suggestion != 'Ben')  # Ben is taken

        for name, problem in [('Ben', 'That name is taken'), ('Robo', 'That name is taken'),
                              ('Abcdefghijk', 'Use 1-10 letters or digits'), ('Ben Ten', 'Use 1-10 letters or digits')]:
            response = self.client.post(reverse('choose_name'), {'username': name})
            self.assertContains(response, problem)
        self.assertEqual(User.objects.count(), 1)

    def test_choosing_a_name_needs_a_google_sign_in_first(self):
        self.assertRedirects(self.client.get(reverse('choose_name')), reverse('landing'))

    def test_a_pin_player_links_google_from_their_profile(self):
        cara = User.objects.create_user(username='Cara', password='1234')
        self.client.force_login(cara)
        response = self.sign_in(google_account(sub='g-3'))
        self.assertEqual(response.json(), {'next': reverse('my_profile')})
        cara.profile.refresh_from_db()
        self.assertEqual((cara.profile.google_sub, cara.profile.avatar_url), ('g-3', PICTURE))

    def test_an_account_linked_to_one_google_account_refuses_another(self):
        cara = User.objects.create_user(username='Cara', password='1234')
        PlayerProfile.objects.filter(user=cara).update(google_sub='g-3')
        self.client.force_login(cara)
        response = self.sign_in(google_account(sub='g-4'))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PlayerProfile.objects.get(user=cara).google_sub, 'g-3')

    def test_a_guest_who_signs_in_with_google_gets_their_own_account(self):
        self.client.post(reverse('demo'))
        response = self.sign_in(google_account(sub='g-5', given_name='Dev'))
        self.assertEqual(response.json(), {'next': reverse('choose_name')})

    def test_a_bad_credential_gets_an_error_not_a_sign_in(self):
        with mock.patch('accounts.google.verify', side_effect=google.InvalidCredential('expired')):
            response = self.client.post(reverse('google_sign_in'), {'credential': 'old'})
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())
        self.assertIsNone(self.signed_in_as())

    def test_sign_in_needs_a_post(self):
        self.assertEqual(self.client.get(reverse('google_sign_in')).status_code, 405)


class GoogleButtonTests(TestCase):
    @override_settings(GOOGLE_CLIENT_ID='test-client')
    def test_the_button_shows_once_a_client_id_is_set(self):
        self.assertContains(self.client.get(reverse('landing')), 'data-client_id="test-client"')

    @override_settings(GOOGLE_CLIENT_ID='')
    def test_without_one_the_page_is_as_before(self):
        self.assertNotContains(self.client.get(reverse('landing')), 'g_id_onload')

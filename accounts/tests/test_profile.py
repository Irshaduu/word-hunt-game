"""
Tests for profiles and the privacy page:
- a profile shows the player's numbers and recent games, with links to the others in them
- profiles are for signed-in players; your own name opens your own profile
- deleting your account removes it and what was kept about it, and only when confirmed
- the privacy page is open to everyone
"""

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from game.models import Match, MatchPlayer


class ProfileTests(TestCase):
    def setUp(self):
        self.asha = User.objects.create_user(username='Asha', password='1234')
        self.ben = User.objects.create_user(username='Ben', password='1234')
        match = Match.objects.create(room_code='ABC', started_at=timezone.now() - timedelta(minutes=5))
        MatchPlayer.objects.create(match=match, user=self.asha, place=1, words_found=7, seconds_left=42)
        MatchPlayer.objects.create(match=match, user=self.ben, place=2, words_found=5, seconds_left=0)
        self.client.force_login(self.asha)

    def test_your_profile_shows_your_recent_games_and_who_was_in_them(self):
        page = self.client.get(reverse('my_profile'))
        self.assertContains(page, '1st')
        self.assertContains(page, 'of 2 · 7 words · 42s left')
        self.assertContains(page, f'href="{reverse("profile", args=["Ben"])}"')
        self.assertEqual(page.context['games_played'], 1)
        self.assertContains(page, 'Delete my account')

    def test_someone_elses_profile_has_no_account_controls(self):
        page = self.client.get(reverse('profile', args=['Ben']))
        self.assertContains(page, '2nd')
        self.assertNotContains(page, 'Delete my account')

    def test_your_own_name_opens_your_own_profile(self):
        self.assertRedirects(self.client.get(reverse('profile', args=['Asha'])), reverse('my_profile'))

    def test_profiles_are_for_signed_in_players(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('profile', args=['Ben'])).status_code, 302)
        self.assertEqual(self.client.get(reverse('my_profile')).status_code, 302)

    def test_an_unknown_name_is_not_found(self):
        self.assertEqual(self.client.get(reverse('profile', args=['Nobody'])).status_code, 404)

    def test_deleting_your_account_removes_it_and_its_games(self):
        response = self.client.post(reverse('delete_account'), {'confirm': 'yes'}, follow=True)
        self.assertContains(response, 'everything kept about it are deleted')
        self.assertFalse(User.objects.filter(username='Asha').exists())
        self.assertFalse(MatchPlayer.objects.filter(user__username='Asha').exists())
        self.assertTrue(MatchPlayer.objects.filter(user=self.ben).exists())  # Ben's result stays
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_nothing_is_deleted_without_confirming(self):
        self.client.post(reverse('delete_account'))
        self.assertTrue(User.objects.filter(username='Asha').exists())


class PrivacyTests(TestCase):
    def test_the_privacy_page_is_open_to_everyone(self):
        self.assertContains(self.client.get(reverse('privacy')), 'What it keeps')

"""
Tests for the friends page and its buttons:
- the page lists friends with their status, requests both ways, and blocks
- adding by name sends a request and tells the other player's open pages
- an unknown name says so
- accept tells both players' open pages to reload their friends
- buttons on a profile go back to it, and never to another site
- block and unblock work from a profile; someone who blocked you is nowhere to be found
- demo guests are told friends need a name; the home page counts friend requests
"""

import asyncio

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from social import presence, rules
from social.models import Block, FriendRequest


class OpenPage:
    """A stand-in for a player's open page: it joins their /ws/me/ group and keeps what arrives."""

    def __init__(self, user):
        self.layer = get_channel_layer()
        self.channel = async_to_sync(self.layer.new_channel)()
        async_to_sync(self.layer.group_add)(presence.group(user.id), self.channel)

    def received(self):
        async def drain():
            messages = []
            while True:
                try:
                    messages.append(await asyncio.wait_for(self.layer.receive(self.channel), timeout=0.05))
                except asyncio.TimeoutError:
                    return messages
        return async_to_sync(drain)()


class FriendsPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.asha = User.objects.create_user(username='Asha', password='1234')
        self.ben = User.objects.create_user(username='Ben', password='1234')
        self.client.force_login(self.asha)

    def test_the_page_lists_friends_requests_and_blocks(self):
        cara, dev, eve = (User.objects.create_user(username=n) for n in ('Cara', 'Dev', 'Eve'))
        rules.send_request(self.ben, self.asha)           # asking Asha
        rules.send_request(self.asha, cara)               # Asha asked
        rules.send_request(dev, self.asha)
        rules.accept(self.asha, dev)                      # friends
        rules.block(self.asha, eve)

        page = self.client.get(reverse('friends'))
        self.assertContains(page, 'Asking to be your friend')
        self.assertContains(page, reverse('friend_action', args=['accept', 'Ben']))
        self.assertContains(page, 'data-friend="Dev" data-status="offline"')
        self.assertContains(page, reverse('friend_action', args=['cancel', 'Cara']))
        self.assertContains(page, reverse('friend_action', args=['unblock', 'Eve']))

    def test_adding_by_name_sends_a_request_and_tells_their_pages(self):
        ben_pages = OpenPage(self.ben)
        response = self.client.post(reverse('add_friend'), {'name': 'ben'}, follow=True)
        self.assertContains(response, 'Friend request sent to Ben.')
        self.assertTrue(FriendRequest.objects.filter(from_user=self.asha, to_user=self.ben).exists())
        self.assertEqual(ben_pages.received(), [{'type': 'friend_request', 'from': 'Asha'}])

    def test_an_unknown_name_says_so(self):
        response = self.client.post(reverse('add_friend'), {'name': 'Nobody'}, follow=True)
        self.assertContains(response, 'No player is called Nobody.')
        self.assertFalse(FriendRequest.objects.exists())

    def test_accepting_tells_both_players_pages(self):
        rules.send_request(self.ben, self.asha)
        asha_pages, ben_pages = OpenPage(self.asha), OpenPage(self.ben)
        self.client.post(reverse('friend_action', args=['accept', 'Ben']))
        self.assertTrue(rules.are_friends(self.asha, self.ben))
        self.assertEqual(asha_pages.received(), [{'type': 'friends_changed'}])
        self.assertEqual(ben_pages.received(), [{'type': 'friends_changed'}])

    def test_buttons_on_a_profile_go_back_to_it(self):
        response = self.client.post(reverse('add_friend'), {'name': 'Ben', 'next': '/u/Ben/'})
        self.assertRedirects(response, '/u/Ben/')

    def test_a_button_never_goes_to_another_site(self):
        response = self.client.post(reverse('add_friend'), {'name': 'Ben', 'next': 'https://example.com/'})
        self.assertRedirects(response, reverse('friends'))

    def test_block_and_unblock_from_a_profile(self):
        self.client.post(reverse('friend_action', args=['block', 'Ben']), {'next': '/u/Ben/'})
        self.assertTrue(Block.objects.filter(blocker=self.asha, blocked=self.ben).exists())
        self.assertContains(self.client.get('/u/Ben/'), 'You blocked Ben')
        self.client.post(reverse('friend_action', args=['unblock', 'Ben']))
        self.assertFalse(Block.objects.exists())

    def test_someone_who_blocked_you_is_nowhere_to_be_found(self):
        rules.block(self.ben, self.asha)
        self.assertEqual(self.client.get('/u/Ben/').status_code, 404)

    def test_a_profile_has_an_add_friend_button(self):
        self.assertContains(self.client.get('/u/Ben/'), 'Add friend')

    def test_an_unknown_action_is_not_found(self):
        self.assertEqual(self.client.post(reverse('friend_action', args=['hug', 'Ben'])).status_code, 404)

    def test_demo_guests_are_told_friends_need_a_name(self):
        self.client.logout()
        self.client.post(reverse('demo'))
        self.assertContains(self.client.get(reverse('friends')), 'Friends are for players with a name')

    def test_friends_need_signing_in(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('friends')).status_code, 302)

    def test_the_home_page_counts_friend_requests(self):
        rules.send_request(self.ben, self.asha)
        self.assertEqual(self.client.get(reverse('landing')).context['friend_requests'], 1)

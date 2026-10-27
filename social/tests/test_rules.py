"""
Tests for the friendship rules (social/rules.py):
- a request, then accept, makes friends, and the request is gone
- two requests that cross make friends at once
- asking twice, or asking a friend, changes nothing
- nobody can ask themselves, a demo guest, or anyone across a block (either way)
- blocking ends a friendship and its requests; after unblocking, a new request works
- requests are limited per player per day
- answering a request that isn't there does nothing
"""

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase

from social import rules
from social.models import FriendRequest, Friendship


class FriendRuleTests(TestCase):
    def setUp(self):
        cache.clear()  # the daily request counts live in the cache
        self.asha = User.objects.create_user(username='Asha')
        self.ben = User.objects.create_user(username='Ben')

    def test_a_request_then_accept_makes_friends(self):
        self.assertEqual(rules.send_request(self.asha, self.ben), rules.SENT)
        self.assertEqual(rules.relationship(self.asha, self.ben), 'sent')
        self.assertEqual(rules.relationship(self.ben, self.asha), 'received')
        self.assertTrue(rules.accept(self.ben, self.asha))
        self.assertTrue(rules.are_friends(self.asha, self.ben))
        self.assertEqual(rules.relationship(self.ben, self.asha), 'friends')
        self.assertFalse(FriendRequest.objects.exists())
        self.assertEqual(rules.friend_ids(self.asha), {self.ben.id})
        self.assertEqual(list(rules.friends_of(self.ben)), [self.asha])

    def test_requests_that_cross_make_friends_at_once(self):
        rules.send_request(self.asha, self.ben)
        self.assertEqual(rules.send_request(self.ben, self.asha), rules.NOW_FRIENDS)
        self.assertTrue(rules.are_friends(self.asha, self.ben))
        self.assertFalse(FriendRequest.objects.exists())

    def test_asking_twice_or_asking_a_friend_changes_nothing(self):
        rules.send_request(self.asha, self.ben)
        self.assertEqual(rules.send_request(self.asha, self.ben), rules.ALREADY_SENT)
        rules.accept(self.ben, self.asha)
        self.assertEqual(rules.send_request(self.ben, self.asha), rules.ALREADY_FRIENDS)
        self.assertEqual(Friendship.objects.count(), 1)

    def test_some_requests_are_not_allowed(self):
        guest = User.objects.create_user(username='Guest0001')
        guest.profile.is_guest = True
        guest.profile.save()
        self.assertEqual(rules.send_request(self.asha, self.asha), rules.NOT_ALLOWED)
        self.assertEqual(rules.send_request(self.asha, guest), rules.NOT_ALLOWED)
        self.assertEqual(rules.send_request(guest, self.asha), rules.NOT_ALLOWED)
        rules.block(self.ben, self.asha)
        self.assertEqual(rules.send_request(self.asha, self.ben), rules.NOT_ALLOWED)
        self.assertEqual(rules.send_request(self.ben, self.asha), rules.NOT_ALLOWED)
        self.assertFalse(FriendRequest.objects.exists())

    def test_blocking_ends_a_friendship_and_its_requests(self):
        rules.send_request(self.asha, self.ben)
        rules.accept(self.ben, self.asha)
        cara = User.objects.create_user(username='Cara')
        rules.send_request(cara, self.asha)

        rules.block(self.asha, self.ben)
        rules.block(self.asha, cara)
        self.assertFalse(rules.are_friends(self.asha, self.ben))
        self.assertFalse(FriendRequest.objects.exists())
        self.assertEqual(rules.relationship(self.asha, self.ben), 'blocked')

        self.assertTrue(rules.unblock(self.asha, self.ben))
        self.assertEqual(rules.send_request(self.ben, self.asha), rules.SENT)

    def test_requests_are_limited_per_day(self):
        others = [User.objects.create_user(username=f'Player{i}') for i in range(rules.REQUESTS_PER_DAY + 1)]
        for other in others[:-1]:
            self.assertEqual(rules.send_request(self.asha, other), rules.SENT)
        self.assertEqual(rules.send_request(self.asha, others[-1]), rules.TOO_MANY)

    def test_answering_a_request_that_is_not_there_does_nothing(self):
        self.assertFalse(rules.accept(self.ben, self.asha))
        self.assertFalse(rules.decline(self.ben, self.asha))
        self.assertFalse(rules.cancel(self.asha, self.ben))
        self.assertFalse(rules.unfriend(self.asha, self.ben))
        self.assertFalse(Friendship.objects.exists())

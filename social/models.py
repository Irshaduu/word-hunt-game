from django.contrib.auth.models import User
from django.db import models
from django.db.models import F, Q


class FriendRequest(models.Model):
    """from_user asked to_user to be friends. Deleted once answered."""
    from_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friend_requests_sent')
    to_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='friend_requests_received')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['from_user', 'to_user'], name='one_request_per_pair'),
            models.CheckConstraint(condition=~Q(from_user=F('to_user')), name='no_request_to_self'),
        ]


class Friendship(models.Model):
    """Two players who are friends: one row per pair, the lower user id first."""
    user_a = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    user_b = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user_a', 'user_b'], name='one_friendship_per_pair'),
            models.CheckConstraint(condition=Q(user_a__lt=F('user_b')), name='friendship_lower_id_first'),
        ]


class Block(models.Model):
    """blocker never deals with blocked again: no requests, invites, voice or rooms between them."""
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocks_made')
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['blocker', 'blocked'], name='one_block_per_pair'),
            models.CheckConstraint(condition=~Q(blocker=F('blocked')), name='no_blocking_self'),
        ]

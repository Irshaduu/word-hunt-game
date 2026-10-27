from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class PlayerProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    total_earned_seconds = models.IntegerField(default=0)
    first_places = models.IntegerField(default=0)
    second_places = models.IntegerField(default=0)
    third_places = models.IntegerField(default=0)
    fourth_places = models.IntegerField(default=0)
    fifth_places = models.IntegerField(default=0)
    # A one-tap demo account: kept off the global leaderboard and deleted after a day.
    is_guest = models.BooleanField(default=False)
    # Google sign-in: the account's stable Google id ("sub"), and its picture on Google's CDN.
    # No email is kept: the game never needs one.
    google_sub = models.CharField(max_length=64, unique=True, null=True, blank=True)
    avatar_url = models.URLField(max_length=500, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"


class Match(models.Model):
    """A finished game between people. Practice games against Robo aren't kept."""
    room_code = models.CharField(max_length=3)
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.room_code} at {self.ended_at:%Y-%m-%d %H:%M}'


class MatchPlayer(models.Model):
    """One player's result in a Match."""
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='results')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='match_results')
    place = models.PositiveSmallIntegerField()        # 1 = winner
    words_found = models.PositiveSmallIntegerField()
    seconds_left = models.PositiveSmallIntegerField()  # the time bank at the end, whole seconds

    class Meta:
        ordering = ['place']
        constraints = [models.UniqueConstraint(fields=['match', 'user'], name='one_result_per_player')]


# Automatically create a profile when a User is created. Changes to a profile are saved where
# they're made: re-saving it whenever its User was saved (every sign-in, for one) could write a
# stale copy back over newer stats or a Google link.
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        PlayerProfile.objects.create(user=instance)


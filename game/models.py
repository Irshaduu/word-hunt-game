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

    def __str__(self):
        return f"{self.user.username}'s Profile"

# Automatically create a profile when a User is created
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        PlayerProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

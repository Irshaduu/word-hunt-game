from django.contrib.auth.models import User
from django.db import models


class Report(models.Model):
    """Someone reported someone in a voice room. Kept so the game's owner can look into it.

    List them with: python manage.py list_reports
    """
    reporter = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='reports_made')
    reported = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reports_about')
    room_name = models.CharField(max_length=40)
    reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reported} in "{self.room_name}" ({self.created_at:%Y-%m-%d %H:%M})'

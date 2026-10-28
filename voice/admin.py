from django.contrib import admin

from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'reported', 'room_name', 'reporter', 'reason')
    list_select_related = ('reported', 'reporter')

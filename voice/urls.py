from django.urls import path

from . import views

urlpatterns = [
    path('voice/ice/', views.ice_servers, name='voice_ice'),
]

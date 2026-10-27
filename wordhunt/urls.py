from django.urls import path, include

urlpatterns = [
    path('', include('game.urls')),
    path('', include('accounts.urls')),
]

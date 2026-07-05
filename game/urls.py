from django.urls import path
from django.views.generic import TemplateView
from . import views

urlpatterns = [
    path('', views.landing, name='landing'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('create/', views.create_room, name='create_room'),
    path('join/<str:room_code>/', views.join_room, name='join_room'),
    path('lobby/<str:room_code>/', views.lobby, name='lobby'),
    path('game/<str:room_code>/', views.game_view, name='game_view'),
    path('api/leaderboard/', views.api_leaderboard, name='api_leaderboard'),
    path('api/live-games/', views.api_live_games, name='api_live_games'),
    path('spectate/<str:room_code>/', views.spectate_view, name='spectate_view'),
    path('sw.js', TemplateView.as_view(template_name='game/sw.js', content_type='application/javascript'), name='sw.js'),
]

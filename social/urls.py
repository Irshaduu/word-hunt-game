from django.urls import path

from . import views

urlpatterns = [
    path('friends/', views.friends_page, name='friends'),
    path('friends/add/', views.add_friend, name='add_friend'),
    path('friends/<str:action>/<str:username>/', views.friend_action, name='friend_action'),
    path('play/invite/<str:username>/', views.invite, name='invite'),
]

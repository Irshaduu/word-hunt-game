from django.urls import path

from . import views

urlpatterns = [
    path('auth/google/', views.google_sign_in, name='google_sign_in'),
    path('auth/google/name/', views.choose_name, name='choose_name'),
    path('profile/', views.my_profile, name='my_profile'),
    path('profile/delete/', views.delete_account, name='delete_account'),
    path('u/<str:username>/', views.profile, name='profile'),
    path('privacy/', views.privacy, name='privacy'),
]

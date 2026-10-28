from django.urls import path

from . import views

urlpatterns = [
    path('voice/ice/', views.ice_servers, name='voice_ice'),
    path('rooms/', views.rooms_page, name='voice_rooms'),
    path('rooms/<str:room_id>/', views.room_page, name='voice_room'),
    path('rooms/<str:room_id>/sfu/publish/', views.sfu_publish, name='sfu_publish'),
    path('rooms/<str:room_id>/sfu/pull/', views.sfu_pull, name='sfu_pull'),
    path('rooms/<str:room_id>/sfu/renegotiate/', views.sfu_renegotiate, name='sfu_renegotiate'),
    path('rooms/<str:room_id>/sfu/stop/', views.sfu_stop, name='sfu_stop'),
    path('rooms/<str:room_id>/report/<str:username>/', views.report, name='room_report'),
    path('rooms/<str:room_id>/block/<str:username>/', views.block, name='room_block'),
]

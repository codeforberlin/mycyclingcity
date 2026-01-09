"""
Project: MyCyclingCity
Generation: AI-based

URL configuration for kiosk app.
"""

from django.urls import path
from . import views

app_name = 'kiosk'

urlpatterns = [
    path('playlist/<str:uid>/', views.kiosk_playlist_page, name='kiosk_playlist_page'),
]


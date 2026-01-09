"""
Project: MyCyclingCity
Generation: AI-based

URL configuration for leaderboard app.
"""

from django.urls import path
from . import views

app_name = 'leaderboard'

urlpatterns = [
    path('', views.leaderboard_page, name='leaderboard_page'),
    path('ticker/', views.leaderboard_ticker, name='leaderboard_ticker'),
]


# mcc/game/urls.py

from django.urls import path
from . import views

app_name = 'game'

urlpatterns = [
    path('', views.game_page, name='game_page'),
    
    # HTMX Views
    path('htmx/assignments', views.handle_assignment_form, name='handle_assignment_form'),
    path('htmx/results', views.render_results_table, name='render_results_table'),

    # API Views
    path('api/game/players', views.get_game_players, name='get_game_players'),
    path('api/game/devices', views.get_game_devices, name='get_game_devices'),
    path('api/game/start', views.start_game, name='start_game'),
    path('api/game/data', views.get_game_data, name='get_game_data'),
    path('api/session/end', views.end_session, name='end_session'), # NEU
    path('api/sound/goal_reached', views.serve_goal_sound, name='serve_goal_sound'),
    path('api/game/images', views.get_game_images, name='get_game_images'),
]
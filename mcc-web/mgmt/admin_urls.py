# mcc/mgmt/admin_urls.py

from django.urls import path
from . import admin_views

app_name = 'mgmt'

urlpatterns = [
    path('', admin_views.bulk_create_school, name='bulk_create_school'),
    path('preview/', admin_views.bulk_create_school_preview, name='bulk_create_school_preview'),
]


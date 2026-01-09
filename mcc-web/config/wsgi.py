# mcc/config/wsgi.py

import os
from django.core.wsgi import get_wsgi_application

# Wichtig: Stellt sicher, dass die Anwendung die Settings-Datei im 'config'-Verzeichnis findet.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()


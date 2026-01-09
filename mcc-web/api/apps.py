from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ApiConfig(AppConfig):
    # Behebt die models.W042 Warnung
    default_auto_field = 'django.db.models.BigAutoField'
    
    # Standard-Label
    name = 'api'
    
    verbose_name = _('MCC Core API & Models')


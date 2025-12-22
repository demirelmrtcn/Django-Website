from django.apps import AppConfig
import os


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    
    def ready(self):
        """Django başladığında otomatik fiyat takip scheduler'ını başlat"""
        import sys
        
        # Django'nun auto-reload mekanizması 2 process başlatır
        # Sadece worker process'de çalıştır (RUN_MAIN=true)
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') == 'true':
            from . import scheduler
            scheduler.start()

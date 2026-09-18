from django.apps import AppConfig


class MyappConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'myapp'
    #Djangoが起動したタイミングで signals.py を読み込み
    def ready(self):
        import myapp.signals

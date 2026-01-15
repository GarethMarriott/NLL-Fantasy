# This will make sure the app is always imported when Django starts
# Celery is optional for development, but required for production
try:
    from .celery import app as celery_app
    __all__ = ('celery_app',)
except ImportError:
    # Celery not installed - development mode without async tasks
    pass


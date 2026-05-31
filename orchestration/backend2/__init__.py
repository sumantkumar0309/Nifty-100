"""
Backend 2 - Celery Tasks, Redis Caching, Channel Partner API Authentication
Implements background job scheduling, caching, and secure API access for external partners.
"""

from backend2.celery_app import celery_app

__all__ = ["celery_app"]

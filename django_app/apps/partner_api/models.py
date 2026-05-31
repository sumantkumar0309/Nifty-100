from __future__ import annotations

import secrets
import uuid

import bcrypt
from cryptography.fernet import Fernet
from django.conf import settings
from django.db import models
from django.utils import timezone


class Partner(models.Model):
    class Tier(models.TextChoices):
        BASIC = "BASIC", "Basic"
        PRO = "PRO", "Pro"
        ENTERPRISE = "ENTERPRISE", "Enterprise"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    tier = models.CharField(max_length=20, choices=Tier.choices, default=Tier.BASIC)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.tier})"

    @property
    def is_authenticated(self) -> bool:
        return True


class PartnerAPIKey(models.Model):
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="api_keys")
    key_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    label = models.CharField(max_length=120, default="default")
    secret_hash = models.CharField(max_length=255)
    secret_ciphertext = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["key_id"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.partner.slug}:{self.key_id}"

    @staticmethod
    def _get_fernet() -> Fernet:
        key = settings.API_SECRET_ENCRYPTION_KEY
        if not key:
            raise ValueError("API_SECRET_ENCRYPTION_KEY is required for signing secret storage.")
        return Fernet(key.encode("utf-8"))

    @classmethod
    def create_key_pair(cls, partner: Partner, label: str = "default") -> tuple["PartnerAPIKey", str]:
        plain_secret = secrets.token_urlsafe(48)
        secret_hash = bcrypt.hashpw(plain_secret.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
        secret_ciphertext = cls._get_fernet().encrypt(plain_secret.encode("utf-8")).decode("utf-8")
        key = cls.objects.create(
            partner=partner,
            label=label,
            secret_hash=secret_hash,
            secret_ciphertext=secret_ciphertext,
            is_active=True,
        )
        return key, plain_secret

    def get_signing_secret(self) -> str:
        decrypted = self._get_fernet().decrypt(self.secret_ciphertext.encode("utf-8"))
        return decrypted.decode("utf-8")

    def revoke(self) -> None:
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=["is_active", "revoked_at"])


class APIUsageLog(models.Model):
    api_key = models.ForeignKey(PartnerAPIKey, on_delete=models.CASCADE, related_name="usage_logs")
    endpoint = models.CharField(max_length=255)
    method = models.CharField(max_length=10)
    status_code = models.PositiveSmallIntegerField()
    response_time_ms = models.PositiveIntegerField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_size = models.PositiveIntegerField(default=0)
    response_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["created_at"]), models.Index(fields=["endpoint"])]


class WebhookSubscription(models.Model):
    partner = models.ForeignKey(Partner, on_delete=models.CASCADE, related_name="webhooks")
    url = models.URLField(max_length=500)
    events = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class WebhookEvent(models.Model):
    subscription = models.ForeignKey(WebhookSubscription, on_delete=models.CASCADE, related_name="events_log")
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    attempt_no = models.PositiveSmallIntegerField(default=1)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, default="")
    delivered_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-delivered_at"]

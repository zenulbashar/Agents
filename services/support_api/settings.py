"""Runtime settings + per-app registry for the support API.

Secrets come from the environment (or Vault-injected env). Non-secret app
registry (pinned Ed25519 public keys, webhook URLs, departments, KB paths)
lives in config/support_api.yaml. One pinned public key per app_id — Foundry
never holds client private keys (D6).
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO_ROOT = Path(__file__).resolve().parents[2]

AUDIENCE = "foundry-support"
DEPARTMENTS = ("tech", "sales", "billing")


class ConfigError(RuntimeError):
    pass


def _load_public_key(raw: str) -> Ed25519PublicKey:
    """Accept a PEM SubjectPublicKeyInfo or base64 of the raw 32-byte key."""
    raw = raw.strip()
    if "-----BEGIN" in raw:
        key = serialization.load_pem_public_key(raw.encode())
        if not isinstance(key, Ed25519PublicKey):
            raise ConfigError("pinned key is not Ed25519")
        return key
    decoded = base64.b64decode(raw)
    if len(decoded) != 32:
        raise ConfigError("raw Ed25519 public key must be 32 bytes")
    return Ed25519PublicKey.from_public_bytes(decoded)


@dataclass(frozen=True)
class AppConfig:
    app_id: str
    public_key: Ed25519PublicKey
    hmac_secret: bytes
    webhook_url: str | None
    webhook_secret: bytes | None
    departments: tuple[str, ...]
    kb_dir: Path

    @property
    def public_key_pem(self) -> bytes:
        return self.public_key.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )


@dataclass
class Settings:
    host: str = "0.0.0.0"
    port: int = 8100
    # App-role DSN: RLS-enforced role used by request handlers.
    database_url: str = ""
    # Owner/maintenance DSN: workers, retention sweep, schema apply.
    maintenance_database_url: str = ""
    store_backend: str = "postgres"  # postgres | memory (dev/tests only)
    apps_config_path: Path = REPO_ROOT / "config" / "support_api.yaml"

    anthropic_api_key: str = ""
    model: str = "claude-haiku-4-5-20251001"
    prescreen_model: str = "claude-haiku-4-5-20251001"
    max_reply_tokens: int = 1024

    daily_token_budget: int = 500_000       # per (app_id, tenant_id) per UTC day
    conversation_token_budget: int = 50_000
    subject_rate_per_minute: int = 10

    retention_days: int = 90
    jti_ttl_seconds: int = 600
    retention_interval_seconds: int = 3600
    webhook_poll_seconds: float = 2.0
    webhook_max_attempts: int = 10
    workers_enabled: bool = True

    operator_token: str = ""                # guards /internal/* operator surface
    public_base_url: str = ""               # for ticket deep links in Telegram

    def __post_init__(self) -> None:
        self.apps_config_path = Path(self.apps_config_path)

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        return cls(
            host=env.get("SUPPORT_API_HOST", "0.0.0.0"),
            port=int(env.get("SUPPORT_API_PORT", "8100")),
            database_url=env.get("SUPPORT_DATABASE_URL", ""),
            maintenance_database_url=env.get(
                "SUPPORT_MAINTENANCE_DATABASE_URL", env.get("SUPPORT_DATABASE_URL", "")
            ),
            store_backend=env.get("SUPPORT_STORE", "postgres"),
            apps_config_path=Path(
                env.get("SUPPORT_APPS_CONFIG", str(REPO_ROOT / "config" / "support_api.yaml"))
            ),
            anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
            model=env.get("SUPPORT_MODEL", "claude-haiku-4-5-20251001"),
            prescreen_model=env.get("SUPPORT_PRESCREEN_MODEL", "claude-haiku-4-5-20251001"),
            max_reply_tokens=int(env.get("SUPPORT_MAX_REPLY_TOKENS", "1024")),
            daily_token_budget=int(env.get("SUPPORT_DAILY_TOKEN_BUDGET", "500000")),
            conversation_token_budget=int(env.get("SUPPORT_CONVERSATION_TOKEN_BUDGET", "50000")),
            subject_rate_per_minute=int(env.get("SUPPORT_SUBJECT_RATE_PER_MINUTE", "10")),
            retention_days=int(env.get("SUPPORT_RETENTION_DAYS", "90")),
            workers_enabled=env.get("SUPPORT_WORKERS_ENABLED", "1") not in ("0", "false", "no"),
            operator_token=env.get("SUPPORT_OPERATOR_TOKEN", ""),
            public_base_url=env.get("SUPPORT_PUBLIC_BASE_URL", ""),
        )


@dataclass
class AppRegistry:
    apps: dict[str, AppConfig] = field(default_factory=dict)

    def get(self, app_id: str) -> AppConfig | None:
        return self.apps.get(app_id)

    @classmethod
    def load(cls, path: Path) -> "AppRegistry":
        if not path.exists():
            raise ConfigError(f"apps config not found: {path}")
        doc = yaml.safe_load(path.read_text()) or {}
        apps: dict[str, AppConfig] = {}
        for app_id, spec in (doc.get("apps") or {}).items():
            spec = spec or {}
            key_raw = spec.get("public_key") or os.environ.get(spec.get("public_key_env", ""), "")
            if not key_raw:
                # App stays unregistered until its key is configured; requests 401.
                continue
            hmac_secret = os.environ.get(spec.get("hmac_secret_env", ""), "")
            if not hmac_secret:
                continue
            webhook_secret = os.environ.get(spec.get("webhook_secret_env", ""), "")
            kb_dir = Path(spec.get("kb_dir", f"services/support_api/kb/{app_id}"))
            if not kb_dir.is_absolute():
                kb_dir = REPO_ROOT / kb_dir
            apps[app_id] = AppConfig(
                app_id=app_id,
                public_key=_load_public_key(key_raw),
                hmac_secret=hmac_secret.encode(),
                webhook_url=spec.get("webhook_url") or None,
                webhook_secret=webhook_secret.encode() if webhook_secret else None,
                departments=tuple(spec.get("departments") or DEPARTMENTS),
                kb_dir=kb_dir,
            )
        return cls(apps=apps)

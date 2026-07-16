"""Two-layer request authentication (Contract v1 §2).

Layer 1: Ed25519 compact JWS in Authorization: Bearer — who is chatting.
  - one pinned public key per app_id; algorithm pinned to EdDSA
  - exact iss/aud match, exp/iat with ≤30s skew, TTL ≤60s
  - jti single-use via a unique-indexed consumed-tokens table
  - tenant context is derived ONLY from the verified token
Layer 2: X-Signature = hex(HMAC-SHA256(shared_secret, raw_body)) — integrity.
  - timing-safe compare over the RAW body, before parsing

Both must pass. Bad/missing => 401. Store down => 503, never a soft pass.
"""
from __future__ import annotations

import hashlib
import hmac

import jwt

from .models import AuthContext, Subject
from .settings import AUDIENCE, AppConfig, AppRegistry
from .store import Store

CLOCK_SKEW_SECONDS = 30
MAX_TOKEN_TTL_SECONDS = 60
SUBJECT_ROLES = ("owner", "diner", "anon")


class AuthError(Exception):
    """Any authentication failure => HTTP 401 (no detail leaks to clients)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def verify_hmac(app: AppConfig, raw_body: bytes, signature_header: str | None) -> None:
    if not signature_header:
        raise AuthError("missing X-Signature")
    expected = hmac.new(app.hmac_secret, raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_header.strip().lower()):
        raise AuthError("bad body signature")


def _bearer_token(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise AuthError("missing bearer token")
    return authorization[len("Bearer "):].strip()


def _subject_from_claims(claims: dict) -> Subject:
    sub = claims.get("subject")
    if not isinstance(sub, dict):
        raise AuthError("missing subject")
    role = sub.get("role")
    subject_id = sub.get("id")
    email = sub.get("email")
    if role not in SUBJECT_ROLES or not isinstance(subject_id, str) or not subject_id:
        raise AuthError("invalid subject")
    if role != "anon" and not email:
        raise AuthError("verified email required for non-anon subjects")
    return Subject(role=role, id=subject_id, email=email, name=sub.get("name"))


async def authenticate(
    *,
    authorization: str | None,
    signature: str | None,
    raw_body: bytes,
    registry: AppRegistry,
    store: Store,
) -> AuthContext:
    token = _bearer_token(authorization)

    # Identify the app from unverified claims, then verify strictly against
    # that app's pinned key. Nothing from the unverified pass is trusted
    # beyond key selection.
    try:
        header = jwt.get_unverified_header(token)
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as exc:
        raise AuthError(f"malformed token: {exc}") from exc

    if header.get("alg") != "EdDSA":
        raise AuthError("algorithm not EdDSA")

    app_id = unverified.get("app_id")
    if not isinstance(app_id, str) or not app_id:
        raise AuthError("missing app_id")
    app = registry.get(app_id)
    if app is None:
        raise AuthError("unknown app")

    try:
        claims = jwt.decode(
            token,
            key=app.public_key_pem,
            algorithms=["EdDSA"],  # pinned; anything else is rejected
            audience=AUDIENCE,
            issuer=app_id,
            leeway=CLOCK_SKEW_SECONDS,
            options={"require": ["iss", "aud", "iat", "exp", "jti", "app_id", "tenant_id"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthError(f"token verification failed: {exc}") from exc

    if claims["app_id"] != app_id:
        raise AuthError("app_id mismatch")
    if claims["exp"] - claims["iat"] > MAX_TOKEN_TTL_SECONDS:
        raise AuthError("token TTL exceeds 60s")

    tenant_id = claims.get("tenant_id")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise AuthError("missing tenant_id")

    jti = claims["jti"]
    if not isinstance(jti, str) or not jti:
        raise AuthError("missing jti")
    # Store errors intentionally propagate (StoreUnavailable => 503): a replay
    # check that cannot run must fail closed, not soft-pass.
    if not await store.consume_jti(app_id, jti):
        raise AuthError("jti replayed")

    verify_hmac(app, raw_body, signature)

    return AuthContext(app_id=app_id, tenant_id=tenant_id, subject=_subject_from_claims(claims))

"""§2: Ed25519 verify (pinned alg/key), jti replay, HMAC body signature.
Bad/missing => rejected; store down => fails closed."""
from __future__ import annotations

import pytest

from services.support_api.auth import AuthError, authenticate
from services.support_api.store import MemoryStore, StoreUnavailable

from conftest import HMAC_SECRET, TENANT, auth_headers, mint_token, sign_body

BODY = b'{"hello":"world"}'


async def _auth(registry, store, private_pem, *, body: bytes = BODY,
                signature: str | None = None, token: str | None = None, **token_kwargs):
    headers = auth_headers(private_pem, body, **token_kwargs)
    return await authenticate(
        authorization=f"Bearer {token}" if token else headers["Authorization"],
        signature=signature if signature is not None else headers["X-Signature"],
        raw_body=body,
        registry=registry,
        store=store,
    )


async def test_happy_path_tenant_comes_from_token(registry, store, private_pem):
    ctx = await _auth(registry, store, private_pem)
    assert ctx.app_id == "prompt2eat"
    assert ctx.tenant_id == TENANT
    assert ctx.subject.role == "owner"
    assert ctx.subject.email == "o@example.com"


async def test_non_eddsa_algorithm_rejected(registry, store, private_pem):
    # A token signed HS256 with the app's HMAC secret must never verify —
    # the algorithm is pinned, there is no alg-header trust.
    forged = mint_token(private_pem, algorithm="HS256", key=HMAC_SECRET)
    with pytest.raises(AuthError):
        await _auth(registry, store, private_pem, token=forged)


async def test_wrong_key_rejected(registry, store, private_pem):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    other_pem = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    with pytest.raises(AuthError):
        await _auth(registry, store, private_pem, token=mint_token(other_pem))


async def test_expired_token_rejected(registry, store, private_pem):
    with pytest.raises(AuthError):
        # Expired well beyond the 30s skew allowance.
        await _auth(registry, store, private_pem, iat=1_000_000, exp=1_000_060)


async def test_ttl_over_60s_rejected(registry, store, private_pem):
    with pytest.raises(AuthError):
        await _auth(registry, store, private_pem, ttl=600)


async def test_wrong_audience_rejected(registry, store, private_pem):
    with pytest.raises(AuthError):
        await _auth(registry, store, private_pem, aud="someone-else")


async def test_wrong_issuer_rejected(registry, store, private_pem):
    with pytest.raises(AuthError):
        await _auth(registry, store, private_pem, iss="not-prompt2eat")


async def test_unknown_app_rejected(registry, store, private_pem):
    with pytest.raises(AuthError):
        await _auth(registry, store, private_pem, app_id="unknown-app")


async def test_jti_replay_rejected(registry, store, private_pem):
    token = mint_token(private_pem)
    signature = sign_body(BODY)
    await authenticate(authorization=f"Bearer {token}", signature=signature,
                       raw_body=BODY, registry=registry, store=store)
    with pytest.raises(AuthError, match="replay"):
        await authenticate(authorization=f"Bearer {token}", signature=signature,
                           raw_body=BODY, registry=registry, store=store)


async def test_missing_bearer_rejected(registry, store, private_pem):
    with pytest.raises(AuthError):
        await authenticate(authorization=None, signature=sign_body(BODY),
                           raw_body=BODY, registry=registry, store=store)


async def test_missing_hmac_rejected(registry, store, private_pem):
    with pytest.raises(AuthError):
        await _auth(registry, store, private_pem, signature="")


async def test_tampered_body_rejected(registry, store, private_pem):
    headers = auth_headers(private_pem, BODY)
    with pytest.raises(AuthError):
        await authenticate(authorization=headers["Authorization"],
                           signature=headers["X-Signature"],
                           raw_body=b'{"hello":"tampered"}',
                           registry=registry, store=store)


async def test_anon_subject_without_email_ok(registry, store, private_pem):
    ctx = await _auth(registry, store, private_pem,
                      subject={"role": "anon", "id": "anon_1"})
    assert ctx.subject.role == "anon"


async def test_non_anon_subject_requires_email(registry, store, private_pem):
    with pytest.raises(AuthError):
        await _auth(registry, store, private_pem,
                    subject={"role": "diner", "id": "user_1"})


async def test_replay_store_down_fails_closed(registry, private_pem):
    class DownStore(MemoryStore):
        async def consume_jti(self, app_id, jti):
            raise StoreUnavailable("db is down")

    with pytest.raises(StoreUnavailable):
        await _auth(registry, DownStore(), private_pem)

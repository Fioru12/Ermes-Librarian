"""Verifica della firma dei token OIDC (core/oidc_keys.py, api/auth.py).

Questi test nascono da un bypass reale, non da un'ipotesi. La versione
precedente di `_validate_oidc_jwt` decodificava il payload in base64 e si
fidava di quello che leggeva: `test_a_forged_token_claiming_admin_is_rejected`
riproduce esattamente il token che, prima della correzione, restituiva
`{'username': 'attaccante-esterno', 'role': 'admin'}`.

Gli altri casi coprono i modi classici di aggirare una verifica scritta a
meta': firmare con un'altra chiave, dichiarare `alg: none`, e la confusione
di algoritmo in cui l'attaccante firma con HMAC usando come segreto la chiave
pubblica del provider — che e' pubblica, quindi la conosce.
"""

import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from config import cfg

ISSUER = "https://sso.esempio.it/realms/ermes"
AUDIENCE = "ermes-knowledge"
KID = "chiave-attiva"


def _rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwks_for(private_key, kid=KID):
    """Il JWKS che il provider pubblicherebbe per questa chiave."""
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


@pytest.fixture
def oidc(monkeypatch):
    """Provider OIDC simulato: una chiave, un JWKS servito senza rete."""
    import core.oidc_keys as keys

    private_key = _rsa_key()
    published = _jwks_for(private_key)
    calls: list[str] = []

    def fake_get(url, timeout=None):
        calls.append(url)
        return _FakeResponse(published)

    monkeypatch.setattr(keys, "httpx", type("_H", (), {"get": staticmethod(fake_get), "HTTPError": Exception}))
    test_cfg = cfg.replace(
        OIDC_ENABLED=True,
        OIDC_ISSUER=ISSUER,
        OIDC_AUDIENCE=AUDIENCE,
        OIDC_JWKS_URL=ISSUER + "/protocol/openid-connect/certs",
    )
    monkeypatch.setattr(keys, "cfg", test_cfg)
    keys.reset_key_cache()
    yield type("_Ctx", (), {"key": private_key, "calls": calls, "cfg": test_cfg, "module": keys})
    keys.reset_key_cache()


def _sign(private_key, claims, algorithm="RS256", kid=KID):
    payload = {"iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 600, **claims}
    return jwt.encode(payload, private_key, algorithm=algorithm, headers={"kid": kid})


# ============================================================
# Il caso che deve funzionare
# ============================================================


def test_a_correctly_signed_token_is_accepted(oidc):
    token = _sign(oidc.key, {"preferred_username": "mario.rossi", "roles": ["editor"]})

    claims = oidc.module.verify_signed_claims(token)

    assert claims is not None
    assert claims["preferred_username"] == "mario.rossi"


def test_the_role_mapping_still_works_on_a_verified_token(oidc, monkeypatch):
    import api.auth

    monkeypatch.setattr(api.auth, "cfg", oidc.cfg)
    token = _sign(oidc.key, {"preferred_username": "capo", "roles": ["ermes-admin"], "groups": ["hr"]})

    user = api.auth._validate_oidc_jwt(token)

    assert user == {"username": "capo", "role": "admin", "provider": "oidc", "groups": ["hr"]}


# ============================================================
# Il bypass che questi test esistono per impedire
# ============================================================


def test_a_forged_token_claiming_admin_is_rejected(oidc, monkeypatch):
    """Il token che prima della correzione restituiva un amministratore.

    Nessuna chiave privata: solo header e payload scritti a mano e una firma
    inventata. E' sufficiente saper comporre tre stringhe base64.
    """
    import api.auth

    monkeypatch.setattr(api.auth, "cfg", oidc.cfg)

    def b64(obj):
        raw = json.dumps(obj).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    header = b64({"alg": "RS256", "typ": "JWT", "kid": KID})
    payload = b64(
        {
            "preferred_username": "attaccante-esterno",
            "roles": ["admin"],
            "iss": ISSUER,
            "aud": AUDIENCE,
            "exp": int(time.time()) + 3600,
        }
    )
    forged = f"{header}.{payload}.firma-inventata"

    assert oidc.module.verify_signed_claims(forged) is None
    assert api.auth._validate_oidc_jwt(forged) is None


def test_a_token_signed_with_another_key_is_rejected(oidc):
    """Firma valida, ma di una chiave che il provider non ha pubblicato."""
    intruso = _rsa_key()
    token = _sign(intruso, {"preferred_username": "attaccante", "roles": ["admin"]})

    assert oidc.module.verify_signed_claims(token) is None


def test_alg_none_is_rejected(oidc):
    """`alg: none` dichiara che la firma non serve. Non e' negoziabile dal token."""

    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    token = f"{b64({'alg': 'none', 'kid': KID})}.{b64({'roles': ['admin'], 'exp': int(time.time()) + 60})}."

    assert oidc.module.verify_signed_claims(token) is None


def test_hmac_signed_with_the_public_key_is_rejected(oidc):
    """Confusione di algoritmo.

    Se il verificatore accettasse `HS256` accanto a `RS256`, l'attaccante
    firmerebbe con HMAC usando come segreto la chiave *pubblica* del
    provider: pubblica per definizione, quindi in suo possesso.
    """
    from cryptography.hazmat.primitives import serialization

    public_pem = (
        oidc.key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )

    # Firmato a mano: PyJWT si rifiuta di usare un PEM come segreto HMAC, ma
    # l'attaccante non usa PyJWT — usa hmac, come qui sotto.
    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = b64(
        json.dumps({"roles": ["admin"], "iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 600}).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    signature = b64(hmac.new(public_pem.encode("utf-8"), signing_input, hashlib.sha256).digest())
    token = f"{header}.{payload}.{signature}"

    assert oidc.module.verify_signed_claims(token) is None


# ============================================================
# Claim standard: scadenza, emittente, destinatario
# ============================================================


def test_an_expired_token_is_rejected(oidc):
    token = _sign(oidc.key, {"roles": ["viewer"], "exp": int(time.time()) - 3600})

    assert oidc.module.verify_signed_claims(token) is None


def test_a_token_without_expiry_is_rejected(oidc):
    """Prima della correzione `if exp and exp < now` lasciava passare un
    token senza `exp`, che quindi non scadeva mai."""
    payload = {"iss": ISSUER, "aud": AUDIENCE, "roles": ["admin"]}
    token = jwt.encode(payload, oidc.key, algorithm="RS256", headers={"kid": KID})

    assert oidc.module.verify_signed_claims(token) is None


def test_a_token_from_another_issuer_is_rejected(oidc):
    token = _sign(oidc.key, {"iss": "https://sso.altro-dominio.it/", "roles": ["admin"]})

    assert oidc.module.verify_signed_claims(token) is None


def test_a_token_for_another_audience_is_rejected(oidc):
    token = _sign(oidc.key, {"aud": "un-altra-applicazione", "roles": ["admin"]})

    assert oidc.module.verify_signed_claims(token) is None


def test_an_unknown_kid_is_rejected(oidc):
    token = _sign(oidc.key, {"roles": ["admin"]}, kid="chiave-mai-pubblicata")

    assert oidc.module.verify_signed_claims(token) is None


# ============================================================
# Fail closed
# ============================================================


def test_verification_fails_closed_when_the_keys_are_unreachable(oidc, monkeypatch):
    """Provider irraggiungibile: si rifiuta, non si ricade sul payload."""

    class _ReteAssenteError(Exception):
        pass

    def exploding_get(url, timeout=None):
        raise _ReteAssenteError("rete assente")

    monkeypatch.setattr(
        oidc.module, "httpx", type("_H", (), {"get": staticmethod(exploding_get), "HTTPError": _ReteAssenteError})
    )
    oidc.module.reset_key_cache()
    token = _sign(oidc.key, {"roles": ["admin"]})

    assert oidc.module.verify_signed_claims(token) is None


def test_verification_fails_closed_without_a_way_to_find_the_keys(oidc, monkeypatch):
    """Ne' JWKS esplicito ne' issuer: non c'e' modo di verificare, quindi si rifiuta."""
    monkeypatch.setattr(oidc.module, "cfg", cfg.replace(OIDC_ENABLED=True, OIDC_ISSUER="", OIDC_JWKS_URL=""))
    oidc.module.reset_key_cache()
    token = _sign(oidc.key, {"roles": ["admin"]})

    assert oidc.module.verify_signed_claims(token) is None


# ============================================================
# Percorso HTTP completo
# ============================================================


def test_the_login_endpoint_refuses_a_forged_token(oidc, monkeypatch, tmp_path):
    """Lo stesso attacco attraverso l'endpoint reale, non solo la funzione."""
    from fastapi.testclient import TestClient

    import api.auth
    from api import app

    app_dir = tmp_path / "app"
    app_dir.mkdir()
    endpoint_cfg = oidc.cfg.replace(BASE_DIR=str(app_dir), API_KEY="")
    monkeypatch.setattr("config.cfg", endpoint_cfg)
    monkeypatch.setattr(api.auth, "cfg", endpoint_cfg)
    api.auth.session_store.clear()

    def b64(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).decode().rstrip("=")

    forged = (
        f"{b64({'alg': 'RS256', 'typ': 'JWT', 'kid': KID})}."
        f"{b64({'preferred_username': 'attaccante-esterno', 'roles': ['admin'], 'iss': ISSUER, 'aud': AUDIENCE, 'exp': int(time.time()) + 3600})}."
        "firma-inventata"
    )

    client = TestClient(app)
    response = client.post("/api/auth/oidc/session", json={"id_token": forged})

    assert response.status_code == 401
    assert api.auth.session_store.count() == 0

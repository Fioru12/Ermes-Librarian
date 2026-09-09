"""Chiave di firma del registro di audit (core/governance.py).

Il threat model presenta la firma HMAC delle voci di audit come la garanzia
che il registro sia a prova di manomissione (T6). Quella garanzia dipende
interamente dal fatto che la chiave non sia nota: se lo e', chiunque abbia il
repository puo' fabbricare una voce che si verifica correttamente, e la firma
smette di dimostrare qualsiasi cosa.

Prima di questi test la chiave era nota in entrambi i casi realistici di
prima installazione:

- senza `.env`, `AUDIT_SECRET` valeva il default del dataclass,
  "ermes-audit-secret-change-in-production", scritto nel repository;
- copiando `.env.example`, valeva "CHANGE_ME_TO_AUDIT_SECRET", altrettanto
  pubblico.

Il codice che genera una chiave casuale per installazione esisteva gia' ma
era irraggiungibile, perche' il default non vuoto faceva vincere sempre il
primo ramo di `_get_audit_secret`.
"""

import json

import pytest

import config
from core.governance import _get_audit_secret, _is_usable_audit_secret, _sign_audit_entry, _verify_audit_signature


@pytest.fixture
def fresh_install(tmp_path, monkeypatch):
    """Installazione nuova: nessuna chiave configurata da nessuna parte."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    monkeypatch.delenv("ERMES_AUDIT_SECRET", raising=False)
    test_cfg = config.cfg.replace(BASE_DIR=str(app_dir), AUDIT_SECRET="")
    monkeypatch.setattr(config, "cfg", test_cfg)
    return test_cfg


# ============================================================
# I valori pubblici non sono chiavi
# ============================================================


@pytest.mark.parametrize(
    "segnaposto",
    [
        "ermes-audit-secret-change-in-production",  # default storico del config
        "CHANGE_ME_TO_AUDIT_SECRET",  # valore di .env.example
        "CHANGE_ME",
        "   ",
        "",
    ],
)
def test_a_public_placeholder_is_not_accepted_as_a_key(segnaposto):
    assert not _is_usable_audit_secret(segnaposto)


def test_a_real_key_is_accepted():
    assert _is_usable_audit_secret("9f2c1a7e4b8d0c3f5a6e2b9d4c7a1f8e")


def test_the_placeholder_is_ignored_in_favour_of_a_generated_key(fresh_install, monkeypatch):
    """Chi copia .env.example senza modificarlo non deve ritrovarsi con una
    chiave pubblica: e' il percorso piu' probabile di una prima installazione."""
    monkeypatch.setattr(config, "cfg", fresh_install.replace(AUDIT_SECRET="CHANGE_ME_TO_AUDIT_SECRET"))

    chiave = _get_audit_secret()

    assert chiave != b"CHANGE_ME_TO_AUDIT_SECRET"
    assert len(chiave) >= 32


# ============================================================
# Installazione nuova
# ============================================================


def test_a_fresh_installation_gets_its_own_random_key(fresh_install):
    chiave = _get_audit_secret()

    assert chiave != b"ermes-audit-secret-change-in-production"
    assert len(chiave) >= 32


def test_the_generated_key_survives_a_restart(fresh_install):
    """Altrimenti tutte le voci precedenti smetterebbero di verificarsi, e per
    chi legge il registro sarebbe indistinguibile da una manomissione."""
    prima = _get_audit_secret()

    dopo = _get_audit_secret()

    assert dopo == prima


def test_two_installations_do_not_share_a_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ERMES_AUDIT_SECRET", raising=False)
    chiavi = []
    for nome in ("azienda-a", "azienda-b"):
        directory = tmp_path / nome
        directory.mkdir()
        monkeypatch.setattr(config, "cfg", config.cfg.replace(BASE_DIR=str(directory), AUDIT_SECRET=""))
        chiavi.append(_get_audit_secret())

    assert chiavi[0] != chiavi[1]


# ============================================================
# Una chiave esplicita resta rispettata
# ============================================================


def test_an_explicit_key_is_used_as_given(fresh_install, monkeypatch):
    """Serve quando piu' istanze devono verificare le stesse voci."""
    monkeypatch.setattr(config, "cfg", fresh_install.replace(AUDIT_SECRET="chiave-aziendale-vera-e-lunga-abcdef"))

    assert _get_audit_secret() == b"chiave-aziendale-vera-e-lunga-abcdef"


# ============================================================
# La firma continua a funzionare
# ============================================================


def test_signing_and_verifying_still_work_with_a_generated_key(fresh_install):
    voce = {"ts": "2026-09-09T10:00:00", "action": "login", "actor": "capo", "detail": {}}
    firmata = dict(voce, signature=_sign_audit_entry(json.dumps(voce, ensure_ascii=False)))

    assert _verify_audit_signature(dict(firmata)) is True


def test_a_tampered_entry_fails_verification(fresh_install):
    """Il punto di tutta la firma: se questo passasse anche da manomessa, la
    chiave generata non servirebbe a niente."""
    voce = {"ts": "2026-09-09T10:00:00", "action": "login", "actor": "capo", "detail": {}}
    firmata = dict(voce, signature=_sign_audit_entry(json.dumps(voce, ensure_ascii=False)))

    manomessa = dict(firmata, actor="qualcun-altro")

    assert _verify_audit_signature(manomessa) is False

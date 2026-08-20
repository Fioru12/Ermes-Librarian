from core.governance import (
    set_user_api_key, authenticate_by_api_key,
    has_min_role, append_audit, verify_audit_log_integrity
)
from core.pii_filter import filter_pii

# ── Test RBAC ──
def test_rbac_hierarchy():
    assert has_min_role('admin', 'viewer')
    assert has_min_role('editor', 'viewer')
    assert not has_min_role('viewer', 'admin')

def test_per_user_api_key_auth():
    # Usa un file temp per non sporcare il vero security/api_keys.json
    key = set_user_api_key('test_user', role='editor')
    user = authenticate_by_api_key(key)
    assert user is not None
    assert user['username'] == 'test_user'
    assert user['role'] == 'editor'

# ── Test PII Filtering ──
def test_pii_filtering():
    text = "Contatta mario.rossi@azienda.it o chiama +39 345 678 9012. CF: RSSMRA85M10A562S"
    filtered = filter_pii(text)
    assert "[EMAIL]" in filtered
    assert "[TELEFONO]" in filtered
    assert "[CODICE_FISCALE]" in filtered
    assert "mario.rossi" not in filtered

# ── Test Audit Integrity ──
def test_audit_integrity(tmp_path):
    audit_file = tmp_path / "audit.jsonl"
    append_audit(str(audit_file), "test_action", "admin", {"data": 123})

    # Verifica
    total, valid = verify_audit_log_integrity(str(audit_file))
    assert total == 1
    assert valid == 1

    # Manomissione
    with open(audit_file, "r+", encoding="utf-8") as f:
        content = f.read()
        f.seek(0)
        f.write(content.replace("123", "999"))

    total, valid = verify_audit_log_integrity(str(audit_file))
    assert total == 1
    assert valid == 0

"""
test_integration.py
Test di integrazione per Ermes - Enterprise Knowledge Hub.
Test flussi critici end-to-end.
"""
import os
import sys
from pathlib import Path

# Aggiungi parent directory al path per importare moduli
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from config import Config
from core.governance import validate_admin_user, validate_password_strength
from core.input_validator import is_safe_module_name, is_safe_string


class TestPasswordValidation:
    """Test validazione password."""

    def test_strong_password(self):
        """Test password forte valida."""
        password = "StrongP@ssw0rd"
        is_valid, msg = validate_password_strength(password)
        assert is_valid, f"Password forte dovrebbe essere valida: {msg}"

    def test_short_password(self):
        """Test password troppo corta."""
        password = "Short1"
        is_valid, msg = validate_password_strength(password)
        assert not is_valid
        assert "8 caratteri" in msg

    def test_no_uppercase(self):
        """Test password senza maiuscole."""
        password = "lowercase1!"
        is_valid, msg = validate_password_strength(password)
        assert not is_valid
        assert "maiuscola" in msg

    def test_no_lowercase(self):
        """Test password senza minuscole."""
        password = "UPPERCASE1!"
        is_valid, msg = validate_password_strength(password)
        assert not is_valid
        assert "minuscola" in msg

    def test_no_number(self):
        """Test password senza numeri."""
        password = "NoNumber!"
        is_valid, msg = validate_password_strength(password)
        assert not is_valid
        assert "numero" in msg

    def test_no_special(self):
        """Test password senza caratteri speciali."""
        password = "NoSpecial1"
        is_valid, msg = validate_password_strength(password)
        assert not is_valid
        assert "speciale" in msg

    def test_empty_password(self):
        """Test password vuota."""
        password = ""
        is_valid, msg = validate_password_strength(password)
        assert not is_valid
        assert "vuota" in msg


class TestAdminUserValidation:
    """Test validazione utente admin."""

    def test_valid_admin_user(self):
        """Test utente admin valido."""
        admin_user = {"username": "admin", "role": "admin"}
        assert validate_admin_user(admin_user) is True

    def test_none_admin_user(self):
        """Test admin_user None."""
        assert validate_admin_user(None) is False

    def test_invalid_structure(self):
        """Test struttura invalida."""
        assert validate_admin_user("not_a_dict") is False
        assert validate_admin_user([]) is False

    def test_missing_username(self):
        """Test username mancante."""
        admin_user = {"role": "admin"}
        assert validate_admin_user(admin_user) is False

    def test_missing_role(self):
        """Test ruolo mancante."""
        admin_user = {"username": "admin"}
        assert validate_admin_user(admin_user) is False

    def test_non_admin_role(self):
        """Test ruolo non admin."""
        admin_user = {"username": "user", "role": "viewer"}
        assert validate_admin_user(admin_user) is False


class TestInputValidation:
    """Test validazione input."""

    def test_safe_module_name(self):
        """Test nome modulo sicuro."""
        assert is_safe_module_name("WinSarp") is True
        assert is_safe_module_name("my_module") is True
        assert is_safe_module_name("Module-123") is True

    def test_unsafe_module_name(self):
        """Test nome modulo non sicuro."""
        assert is_safe_module_name("../../../etc/passwd") is False
        assert is_safe_module_name("module<script>") is False
        assert is_safe_module_name("") is False
        assert is_safe_module_name(None) is False

    def test_safe_string(self):
        """Test stringa sicura."""
        assert is_safe_string("normal text") is True
        assert is_safe_string("test123") is True

    def test_unsafe_string(self):
        """Test stringa non sicura."""
        assert is_safe_string("../../../etc/passwd") is False
        assert is_safe_string("test<script>") is False
        assert is_safe_string("") is False


class TestConfigDefaults:
    """Test configurazione default."""

    def test_config_initialization(self):
        """Test inizializzazione configurazione."""
        cfg = Config()
        assert cfg.HOST is not None
        assert cfg.PORT is not None
        assert cfg.DEFAULT_MODEL_ID is not None
        assert cfg.EMBED_MODEL_ID is not None

    def test_config_paths(self):
        """Test percorsi configurazione."""
        cfg = Config()
        assert cfg.DOCS_DIR is not None
        assert cfg.CHROMA_DIR is not None
        assert cfg.LOGS_DIR is not None
        assert cfg.SECURITY_DIR is not None


# =========================================================================
# INTEGRAZIONE REALE (Ollama, ChromaDB, moduli core)
# =========================================================================


@pytest.mark.skipif(
    not os.environ.get("ERMES_TEST_INTEGRATION"),
    reason="Abilita con ERMES_TEST_INTEGRATION=1 per test reali",
)
class TestRealOllama:
    """Test reali contro Ollama."""

    def test_ollama_available(self):
        import requests
        try:
            r = requests.get("http://127.0.0.1:11434/api/tags", timeout=5)
            assert r.status_code == 200
            models = r.json().get("models", [])
            assert len(models) > 0
        except (requests.ConnectionError, requests.Timeout):
            pytest.skip("Ollama non raggiungibile")


@pytest.mark.skipif(
    not os.environ.get("ERMES_TEST_INTEGRATION"),
    reason="Abilita con ERMES_TEST_INTEGRATION=1 per test reali",
)
class TestRealChromaDB:
    """Test reali contro ChromaDB."""

    def test_chromadb_create_and_query(self):
        import tempfile

        import chromadb
        tmpdir = tempfile.mkdtemp()
        try:
            client = chromadb.PersistentClient(path=tmpdir)
            coll = client.create_collection("test_coll")
            coll.add(ids=["1", "2"], documents=["test one", "test two"])
            results = coll.query(query_texts=["test"], n_results=2)
            assert len(results["ids"][0]) == 2
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

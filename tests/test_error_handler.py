"""
test_error_handler.py
Test unitari per il modulo error_handler.
"""
import pytest

from core.error_handler import (
    AppError,
    ConfigError,
    DocumentError,
    ErrorLevel,
    OllamaError,
    RAGIndexError,
    handle_config_error,
    handle_document_error,
    handle_index_error,
    handle_ollama_error,
    log_error,
    safe_call,
)


class TestErrorClasses:
    """Test per le classi di errore custom."""

    def test_app_error_creation(self):
        """Test creazione AppError."""
        error = AppError("Test error", ErrorLevel.WARNING, {"key": "value"})
        assert str(error) == "Test error"
        assert error.level == ErrorLevel.WARNING
        assert error.context == {"key": "value"}

    def test_app_error_default_level(self):
        """Test AppError con livello di default."""
        error = AppError("Test error")
        assert error.level == ErrorLevel.ERROR
        assert error.context == {}

    def test_ollama_error_inheritance(self):
        """Test che OllamaError eredita da AppError."""
        error = OllamaError("Ollama error")
        assert isinstance(error, AppError)
        assert str(error) == "Ollama error"

    def test_index_error_inheritance(self):
        """Test che RAGIndexError eredita da AppError."""
        error = RAGIndexError("Index error")
        assert isinstance(error, AppError)

    def test_document_error_inheritance(self):
        """Test che DocumentError eredita da AppError."""
        error = DocumentError("Document error")
        assert isinstance(error, AppError)

    def test_config_error_inheritance(self):
        """Test che ConfigError eredita da AppError."""
        error = ConfigError("Config error")
        assert isinstance(error, AppError)


class TestHandleOllamaError:
    """Test per handle_ollama_error."""

    def test_connection_refused(self):
        """Test errore di connessione rifiutata."""
        error = Exception("Connection refused")
        success, msg = handle_ollama_error(error)
        assert not success
        assert "Ollama non è in esecuzione" in msg

    def test_not_found(self):
        """Test errore not found."""
        error = Exception("Model not found")
        success, msg = handle_ollama_error(error)
        assert not success
        assert "Ollama non è in esecuzione" in msg

    def test_timeout(self):
        """Test errore di timeout."""
        error = Exception("Request timeout")
        success, msg = handle_ollama_error(error)
        assert not success
        assert "timeout" in msg.lower()

    def test_model_error(self):
        """Test errore relativo al modello."""
        error = Exception("Model qwen not available")
        success, msg = handle_ollama_error(error)
        assert not success
        assert "Modello AI non trovato" in msg

    def test_generic_error(self):
        """Test errore generico."""
        error = Exception("Some other error")
        success, msg = handle_ollama_error(error)
        assert not success
        assert "Errore Ollama" in msg


class TestHandleIndexError:
    """Test per handle_index_error."""

    def test_embedding_error(self):
        """Test errore di embedding."""
        error = Exception("Embedding dimension mismatch")
        success, msg = handle_index_error(error, "test_module")
        assert not success
        assert "embeddings" in msg.lower()

    def test_disk_space(self):
        """Test errore di spazio disco."""
        error = Exception("No disk space left")
        success, msg = handle_index_error(error)
        assert not success
        assert "spazio disco" in msg.lower()

    def test_lock_timeout(self):
        """Test errore di lock timeout."""
        error = Exception("Lock acquisition timeout")
        success, msg = handle_index_error(error)
        assert not success
        assert "timeout" in msg.lower()

    def test_generic_error(self):
        """Test errore generico."""
        error = Exception("Some index error")
        success, msg = handle_index_error(error, "test_module")
        assert not success
        assert "Errore generazione indice" in msg


class TestHandleDocumentError:
    """Test per handle_document_error."""

    def test_file_not_found(self):
        """Test file non trovato."""
        error = Exception("File not found")
        success, msg = handle_document_error(error, "test.pdf")
        assert not success
        assert "non trovato" in msg

    def test_permission_denied(self):
        """Test permessi negati."""
        error = Exception("Permission denied")
        success, msg = handle_document_error(error, "test.pdf")
        assert not success
        assert "Permessi insufficienti" in msg

    def test_corrupted_file(self):
        """Test file corrotto."""
        error = Exception("Corrupted file format")
        success, msg = handle_document_error(error, "test.pdf")
        assert not success
        assert "danneggiato" in msg.lower() or "corrotto" in msg.lower()

    def test_encoding_error(self):
        """Test errore di encoding."""
        error = Exception("UnicodeDecodeError: invalid encoding")
        success, msg = handle_document_error(error, "test.txt")
        assert not success
        assert "encoding" in msg.lower() or "danneggiato" in msg.lower()

    def test_generic_error(self):
        """Test errore generico."""
        error = Exception("Some document error")
        success, msg = handle_document_error(error, "test.pdf")
        assert not success
        assert "Errore lettura documento" in msg


class TestHandleConfigError:
    """Test per handle_config_error."""

    def test_config_error(self):
        """Test errore di configurazione."""
        error = Exception("Invalid config value")
        success, msg = handle_config_error(error, "DATABASE_URL")
        assert not success
        assert "Errore configurazione" in msg
        assert "DATABASE_URL" in msg


class TestSafeCall:
    """Test per safe_call."""

    def test_successful_call(self):
        """Test chiamata riuscita."""
        def success_func():
            return 42

        result = safe_call(success_func)
        assert result == 42

    def test_successful_call_with_args(self):
        """Test chiamata riuscita con argomenti."""
        def add(a, b):
            return a + b

        result = safe_call(add, 5, 3)
        assert result == 8

    def test_failed_call_returns_default(self):
        """Test che una chiamata fallita restituisce il default."""
        def failing_func():
            raise ValueError("Test error")

        result = safe_call(failing_func, default_return="fallback")
        assert result == "fallback"

    def test_failed_call_returns_none_by_default(self):
        """Test che una chiamata fallita restituisce None per default."""
        def failing_func():
            raise ValueError("Test error")

        result = safe_call(failing_func)
        assert result is None

    def test_failed_call_with_error_handler(self):
        """Test che l'error handler viene chiamato."""
        def failing_func():
            raise ValueError("Test error")

        errors = []
        def error_handler(e):
            errors.append(str(e))

        safe_call(failing_func, error_handler=error_handler)
        assert len(errors) == 1
        assert "Test error" in errors[0]


class TestLogError:
    """Test per log_error."""

    def test_log_error_returns_dict(self):
        """Test che log_error restituisce un dizionario."""
        result = log_error("Test message")
        assert isinstance(result, dict)
        assert result["message"] == "Test message"
        assert result["level"] == "error"

    def test_log_error_with_exception(self):
        """Test log_error con eccezione."""
        error = ValueError("Test exception")
        result = log_error("Error occurred", error=error, level=ErrorLevel.WARNING)
        assert result["error"] == "Test exception"
        assert result["level"] == "warning"

    def test_log_error_with_context(self):
        """Test log_error con contesto."""
        # Usa chiavi che non entrano in conflitto con LogRecord
        context = {"component": "test", "user": "admin"}
        result = log_error("Error with context", context=context)
        assert result["context"] == context


class TestErrorLevels:
    """Test per i livelli di errore."""

    def test_error_levels_values(self):
        """Test che i livelli di errore hanno i valori corretti."""
        assert ErrorLevel.INFO.value == "info"
        assert ErrorLevel.WARNING.value == "warning"
        assert ErrorLevel.ERROR.value == "error"
        assert ErrorLevel.CRITICAL.value == "critical"


class TestRetryOnError:
    """Test per la funzione retry_on_error."""

    def test_success_no_retry(self):
        """Funzione che riesce subito."""
        from core.error_handler import retry_on_error
        calls = 0
        def ok():
            nonlocal calls
            calls += 1
            return 42
        assert retry_on_error(ok) == 42
        assert calls == 1

    def test_retry_then_succeed(self):
        """Fallisce 2 volte poi riesce."""
        from core.error_handler import retry_on_error
        calls = 0
        def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ValueError("temporary")
            return "ok"
        assert retry_on_error(flaky, max_attempts=5, delay=0.01) == "ok"
        assert calls == 3

    def test_exhaust_retries(self):
        """Esaurisce tutti i tentativi."""
        from core.error_handler import retry_on_error
        calls = 0
        def always_fail():
            nonlocal calls
            calls += 1
            raise RuntimeError("boom")
        with pytest.raises(RuntimeError, match="boom"):
            retry_on_error(always_fail, max_attempts=3, delay=0.01)
        assert calls == 3

    def test_on_retry_callback(self):
        """Callback on_retry viene chiamato."""
        from core.error_handler import retry_on_error
        retries = []
        def fail():
            raise ValueError("nope")
        def cb(attempt, err):
            retries.append((attempt, str(err)))
        with pytest.raises(ValueError):
            retry_on_error(fail, max_attempts=2, delay=0.01, on_retry=cb)
        assert len(retries) == 1
        assert retries[0] == (1, "nope")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

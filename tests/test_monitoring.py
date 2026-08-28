"""core/monitoring.py: aggregazione del log di audit.

analyze_audit e' l'unica funzione ancora raggiungibile dal prodotto
(api/audit.py -> GET /api/audit/stats). Il resto del modulo leggeva log di
sessione in formato session_*.jsonl, una convenzione dell'era WinSarp che il
prodotto attuale non scrive piu' da nessuna parte: rimosso il 21 agosto 2026
insieme a questo file, che testava esclusivamente quel codice morto senza
coprire mai analyze_audit stessa.
"""
import json

from core import monitoring


def _write_entry(audit_file, **fields):
    entry = {"ts": "2026-08-21T10:00:00", "action": "unknown", "actor": "unknown"}
    entry.update(fields)
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def test_missing_audit_file_returns_empty_report(temp_dir):
    result = monitoring.analyze_audit(str(temp_dir / "nessuno.jsonl"))
    assert result == {"total_actions": 0, "actions_by_type": {}, "top_users": []}


def test_counts_actions_by_type_and_top_users(temp_dir):
    audit_file = str(temp_dir / "audit.jsonl")
    _write_entry(audit_file, action="library_created", actor="alice")
    _write_entry(audit_file, action="library_created", actor="alice")
    _write_entry(audit_file, action="document_downloaded", actor="bob")

    result = monitoring.analyze_audit(audit_file)

    assert result["total_actions"] == 3
    assert result["actions_by_type"] == {"library_created": 2, "document_downloaded": 1}
    assert result["top_users"][0] == {"username": "alice", "actions": 2}


def test_entries_older_than_the_window_are_excluded(temp_dir):
    audit_file = str(temp_dir / "audit.jsonl")
    old_ts = "2020-01-01T00:00:00"
    _write_entry(audit_file, ts=old_ts, action="library_created", actor="alice")
    _write_entry(audit_file, action="library_created", actor="bob")

    result = monitoring.analyze_audit(audit_file, days=30)

    assert result["total_actions"] == 1
    assert result["top_users"] == [{"username": "bob", "actions": 1}]


def test_a_malformed_line_does_not_stop_the_rest_of_the_file_from_being_read(temp_dir):
    """Trovato in revisione: un try/except attorno all'intero ciclo (invece che
    per riga) faceva si' che una singola riga corrotta azzerasse silenziosamente
    le statistiche su ogni riga successiva, anche valida — mentre gli altri
    lettori dello stesso file in api/audit.py gestiscono l'errore per riga.
    """
    audit_file = str(temp_dir / "audit.jsonl")
    _write_entry(audit_file, action="library_created", actor="alice")
    with open(audit_file, "a", encoding="utf-8") as f:
        f.write("questa riga non e' JSON valido\n")
    _write_entry(audit_file, action="library_created", actor="alice")

    result = monitoring.analyze_audit(audit_file)

    assert result["total_actions"] == 2

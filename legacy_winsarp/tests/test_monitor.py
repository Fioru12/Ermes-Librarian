"""
test_monitor.py
Test per le funzioni di monitoraggio e KPI di monitor_dashboard.py.
"""
import json
import os
import tempfile
from datetime import datetime, timedelta

from legacy_winsarp.ui.monitor_dashboard import analyze_performance, count_sessions, get_feedback_stats

# ============================================================
# FIXTURES
# ============================================================

def create_session_log(tmpdir, fname, entries=None):
    """Crea un file di sessione per test."""
    path = os.path.join(tmpdir, fname)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if entries:
        with open(path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
    else:
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps({"role": "user", "content": "test"}) + "\n")


# ============================================================
# TEST: count_sessions
# ============================================================

def test_count_sessions_empty_dir():
    """Directory inesistente -> zero sessioni."""
    result = count_sessions("/non/existent/path_xyz_12345")
    assert result["total_sessions"] == 0
    assert result["sessions_today"] == 0
    assert result["sessions_week"] == 0


def test_count_sessions_empty_logs():
    """Directory vuota -> zero sessioni."""
    with tempfile.TemporaryDirectory() as tmp:
        result = count_sessions(tmp)
        assert result["total_sessions"] == 0


def test_count_sessions_non_session_files():
    """Solo file non-sessione ignorati."""
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "other.json"), "w") as f:
            f.write("{}")
        result = count_sessions(tmp)
        assert result["total_sessions"] == 0


def test_count_sessions_single_session():
    """Un file sessione presente."""
    with tempfile.TemporaryDirectory() as tmp:
        create_session_log(tmp, "session_20260522_123456.jsonl")
        result = count_sessions(tmp)
        assert result["total_sessions"] == 1


def test_count_sessions_multiple_sessions():
    """Più file sessione contati correttamente."""
    with tempfile.TemporaryDirectory() as tmp:
        create_session_log(tmp, "session_20260520_000000.jsonl")
        create_session_log(tmp, "session_20260521_000000.jsonl")
        create_session_log(tmp, "session_20260522_000000.jsonl")
        result = count_sessions(tmp)
        assert result["total_sessions"] == 3


def test_count_sessions_today():
    """Sessioni di oggi contate separatamente."""
    today_str = datetime.now().strftime("%Y%m%d")
    with tempfile.TemporaryDirectory() as tmp:
        create_session_log(tmp, f"session_{today_str}_123456.jsonl")
        create_session_log(tmp, "session_20260101_000000.jsonl")
        result = count_sessions(tmp)
        assert result["sessions_today"] == 1
        assert result["total_sessions"] == 2


def test_count_sessions_week():
    """Sessioni dell'ultima settimana contate correttamente."""
    today = datetime.now()
    with tempfile.TemporaryDirectory() as tmp:
        create_session_log(tmp, today.strftime("session_%Y%m%d_000000.jsonl"))
        d3 = (today - timedelta(days=3)).strftime("%Y%m%d")
        create_session_log(tmp, f"session_{d3}_000000.jsonl")
        d10 = (today - timedelta(days=10)).strftime("%Y%m%d")
        create_session_log(tmp, f"session_{d10}_000000.jsonl")

        result = count_sessions(tmp, days=7)
        assert result["sessions_week"] == 2
        assert result["total_sessions"] == 3
        assert result["sessions_today"] == 1


# ============================================================
# TEST: analyze_performance
# ============================================================

def test_analyze_performance_empty():
    """Nessun log -> zero performance."""
    result = analyze_performance("/non/existent/path_789")
    assert result["total_responses"] == 0


def test_analyze_performance_no_times():
    """Log senza elapsed_sec -> zero performance."""
    with tempfile.TemporaryDirectory() as tmp:
        create_session_log(tmp, "session_20260522_000000.jsonl")
        result = analyze_performance(tmp)
        assert result["total_responses"] == 0


def test_analyze_performance_with_times():
    """Log con elapsed_sec calcolano medie."""
    with tempfile.TemporaryDirectory() as tmp:
        entries = [
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "r1", "elapsed_sec": 2.5},
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "r2", "elapsed_sec": 5.0},
        ]
        create_session_log(tmp, "session_20260522_000000.jsonl", entries)
        result = analyze_performance(tmp)
        assert result["total_responses"] == 2
        assert result["avg_response_time_s"] == 3.75
        assert result["min_response_time_s"] == 2.5
        assert result["max_response_time_s"] == 5.0


# ============================================================
# TEST: get_feedback_stats
# ============================================================

def test_get_feedback_stats_empty():
    """Nessun feedback -> zero."""
    session_state = {"other_key": "value"}
    result = get_feedback_stats(session_state)
    assert result["total"] == 0
    assert result["up_votes"] == 0
    assert result["down_votes"] == 0


def test_get_feedback_stats_counts():
    """Feedback contati correttamente."""
    session_state = {
        "feedback_1": "up",
        "feedback_2": "down",
        "feedback_3": "up",
        "not_feedback": "ignore",
    }
    result = get_feedback_stats(session_state)
    assert result["total"] == 3
    assert result["up_votes"] == 2
    assert result["down_votes"] == 1

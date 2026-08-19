import json
import os

from core import monitoring


class TestCountSessions:
    def test_empty_dir_returns_zero(self, temp_dir):
        result = monitoring.count_sessions(str(temp_dir))
        assert result["total_sessions"] == 0
        assert result["sessions_today"] == 0

    def test_counts_session_files(self, temp_dir):
        for name in ["session_20260625_001.jsonl", "session_20260625_002.jsonl"]:
            path = os.path.join(temp_dir, name)
            with open(path, "w") as f:
                f.write("{}")
        result = monitoring.count_sessions(str(temp_dir))
        assert result["total_sessions"] == 2


class TestCountQueries:
    def test_empty_dir(self, temp_dir):
        result = monitoring.count_queries(str(temp_dir))
        assert result["total_queries"] == 0

    def test_queries_in_session(self, temp_dir):
        today = __import__("datetime").datetime.now().strftime("%Y%m%d")
        fpath = os.path.join(temp_dir, f"session_{today}_001.jsonl")
        with open(fpath, "w") as f:
            f.write(json.dumps({"role": "user", "modulo": "winsarp"}) + "\n")
            f.write(json.dumps({"role": "assistant", "modulo": "winsarp"}) + "\n")
            f.write(json.dumps({"role": "user", "modulo": "generic"}) + "\n")
        result = monitoring.count_queries(str(temp_dir))
        assert result["total_queries"] == 2
        assert result["queries_by_module"]["winsarp"] == 1


class TestAnalyzePerformance:
    def test_empty_dir(self, temp_dir):
        result = monitoring.analyze_performance(str(temp_dir))
        assert result["total_responses"] == 0

    def test_with_response_times(self, temp_dir):
        fpath = os.path.join(temp_dir, "session_20260625_001.jsonl")
        with open(fpath, "w") as f:
            f.write(json.dumps({"elapsed_sec": 1.5}) + "\n")
            f.write(json.dumps({"elapsed_sec": 2.5}) + "\n")
        result = monitoring.analyze_performance(str(temp_dir))
        assert result["total_responses"] == 2
        assert result["avg_response_time_s"] == 2.0


class TestGetFeedbackStats:
    def test_no_feedback(self):
        result = monitoring.get_feedback_stats({})
        assert result["up_votes"] == 0
        assert result["down_votes"] == 0

    def test_with_feedback(self):
        state = {"feedback_q1": "up", "feedback_q2": "down", "feedback_q3": "up"}
        result = monitoring.get_feedback_stats(state)
        assert result["up_votes"] == 2
        assert result["down_votes"] == 1
        assert result["total"] == 3


class TestCheckAlerts:
    def test_returns_list(self):
        from config import cfg
        alerts = monitoring.check_alerts(cfg)
        assert isinstance(alerts, list)

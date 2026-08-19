"""
monitoring.py
Metriche di sistema e KPI per Ermes.
Fornisce funzioni per analizzare utilizzo, performance e stato infrastruttura.
"""
import json
import os
import shutil
from collections import defaultdict
from datetime import datetime, timedelta


def count_sessions(logs_dir: str, days: int = 7) -> dict:
    if not os.path.exists(logs_dir):
        return {"total_sessions": 0, "sessions_today": 0, "sessions_week": 0}
    today = datetime.now().date()
    week_ago = today - timedelta(days=days)
    total = 0
    today_count = 0
    week_count = 0
    for fname in os.listdir(logs_dir):
        if fname.endswith(".jsonl") and fname.startswith("session_"):
            total += 1
            try:
                date_str = fname.replace("session_", "").replace(".jsonl", "")
                file_date = datetime.strptime(date_str[:8], "%Y%m%d").date()
                if file_date == today:
                    today_count += 1
                if file_date >= week_ago:
                    week_count += 1
            except (ValueError, IndexError):
                pass
    return {"total_sessions": total, "sessions_today": today_count, "sessions_week": week_count}


def count_queries(logs_dir: str, days: int = 7) -> dict:
    if not os.path.exists(logs_dir):
        return {"total_queries": 0, "queries_today": 0, "queries_by_module": {}}
    today = datetime.now().date()
    week_ago = today - timedelta(days=days)
    total = 0
    today_count = 0
    queries_by_module = defaultdict(int)
    for fname in os.listdir(logs_dir):
        if not fname.endswith(".jsonl") or not fname.startswith("session_"):
            continue
        try:
            date_str = fname.replace("session_", "").replace(".jsonl", "")
            file_date = datetime.strptime(date_str[:8], "%Y%m%d").date()
        except (ValueError, IndexError):
            continue
        if file_date < week_ago:
            continue
        fpath = os.path.join(logs_dir, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("role") == "user":
                        total += 1
                        queries_by_module[entry.get("modulo", "unknown")] += 1
                        if file_date == today:
                            today_count += 1
        except (json.JSONDecodeError, OSError):
            pass
    return {"total_queries": total, "queries_today": today_count, "queries_by_module": dict(queries_by_module)}


def analyze_performance(logs_dir: str, days: int = 7) -> dict:
    if not os.path.exists(logs_dir):
        return {"avg_response_time_s": 0, "max_response_time_s": 0, "min_response_time_s": 0, "total_responses": 0}
    times = []
    week_ago = datetime.now() - timedelta(days=days)
    for fname in os.listdir(logs_dir):
        if not fname.endswith(".jsonl") or not fname.startswith("session_"):
            continue
        fpath = os.path.join(logs_dir, fname)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath))
            if mtime < week_ago:
                continue
        except OSError:
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    elapsed = entry.get("elapsed_sec")
                    if elapsed is not None:
                        times.append(elapsed)
        except (json.JSONDecodeError, OSError):
            pass
    if not times:
        return {"avg_response_time_s": 0, "max_response_time_s": 0, "min_response_time_s": 0, "total_responses": 0}
    return {
        "avg_response_time_s": round(sum(times) / len(times), 2),
        "max_response_time_s": round(max(times), 2),
        "min_response_time_s": round(min(times), 2),
        "total_responses": len(times),
    }


def analyze_audit(audit_file: str, days: int = 30) -> dict:
    if not os.path.exists(audit_file):
        return {"total_actions": 0, "actions_by_type": {}, "top_users": []}
    week_ago = datetime.now() - timedelta(days=days)
    total = 0
    actions_by_type = defaultdict(int)
    users_count = defaultdict(int)
    try:
        with open(audit_file, encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                ts = entry.get("ts", "")
                try:
                    entry_time = datetime.fromisoformat(ts)
                    if entry_time < week_ago:
                        continue
                except (ValueError, TypeError):
                    pass
                total += 1
                action = entry.get("action", "unknown")
                actions_by_type[action] += 1
                users_count[entry.get("actor", "unknown")] += 1
    except (json.JSONDecodeError, OSError):
        pass
    top_users = sorted(users_count.items(), key=lambda x: x[1], reverse=True)[:5]
    return {"total_actions": total, "actions_by_type": dict(actions_by_type), "top_users": [{"username": u, "actions": c} for u, c in top_users]}


def check_infrastructure_status(cfg) -> dict:
    status = {}
    if os.path.exists(cfg.DOCS_DIR):
        moduli = [d for d in os.listdir(cfg.DOCS_DIR) if os.path.isdir(os.path.join(cfg.DOCS_DIR, d))]
        total_files = sum(
            len([f for f in os.listdir(os.path.join(cfg.DOCS_DIR, m)) if os.path.isfile(os.path.join(cfg.DOCS_DIR, m, f))])
            for m in moduli
        )
        status["documents"] = {"modules": len(moduli), "module_names": moduli, "total_files": total_files}
    else:
        status["documents"] = {"modules": 0, "module_names": [], "total_files": 0}
    if os.path.exists(cfg.CHROMA_DIR):
        chroma_dirs = [d for d in os.listdir(cfg.CHROMA_DIR) if os.path.isdir(os.path.join(cfg.CHROMA_DIR, d))]
        status["chroma"] = {"collections": len(chroma_dirs), "names": chroma_dirs}
    else:
        status["chroma"] = {"collections": 0, "names": []}
    if os.path.exists(cfg.LOGS_DIR):
        session_logs = len([f for f in os.listdir(cfg.LOGS_DIR) if f.endswith(".jsonl") and f.startswith("session_")])
        has_audit = os.path.exists(cfg.AUDIT_FILE)
        status["logs"] = {"sessions": session_logs, "has_audit": has_audit}
    else:
        status["logs"] = {"sessions": 0, "has_audit": False}
    if os.path.exists(cfg.USERS_FILE):
        try:
            with open(cfg.USERS_FILE, encoding="utf-8") as f:
                data = json.load(f)
            users = data.get("users", [])
            status["security"] = {
                "total_users": len(users),
                "admins": len([u for u in users if u.get("role") == "admin"]),
                "viewers": len([u for u in users if u.get("role") == "viewer"]),
            }
        except (json.JSONDecodeError, OSError):
            status["security"] = {"total_users": 0, "admins": 0, "viewers": 0}
    else:
        status["security"] = {"total_users": 0, "admins": 0, "viewers": 0}
    total_size = 0
    for path, _ in [(cfg.DOCS_DIR, "documenti"), (cfg.CHROMA_DIR, "chroma_db"), (cfg.LOGS_DIR, "logs")]:
        if os.path.exists(path):
            for dirpath, _, filenames in os.walk(path):
                for f in filenames:
                    try:
                        fp = os.path.join(dirpath, f)
                        total_size += os.path.getsize(fp)
                    except OSError:
                        pass
    status["disk_usage_mb"] = round(total_size / (1024 * 1024), 1)
    return status


def get_feedback_stats(session_state: dict) -> dict:
    up_count = 0
    down_count = 0
    for key, value in session_state.items():
        if key.startswith("feedback_"):
            if value == "up":
                up_count += 1
            elif value == "down":
                down_count += 1
    return {"up_votes": up_count, "down_votes": down_count, "total": up_count + down_count}


def generate_full_report(cfg) -> dict:
    report = {
        "timestamp": datetime.now().isoformat(),
        "sessions": count_sessions(cfg.LOGS_DIR),
        "queries": count_queries(cfg.LOGS_DIR),
        "performance": analyze_performance(cfg.LOGS_DIR),
        "audit": analyze_audit(cfg.AUDIT_FILE),
        "infrastructure": check_infrastructure_status(cfg),
    }
    return report


def export_report_to_json(report: dict, filepath: str = "logs/dashboard_report.json"):
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def get_daily_trends(logs_dir: str, days: int = 7) -> list[dict]:
    from collections import defaultdict
    if not os.path.exists(logs_dir):
        return []
    daily = defaultdict(lambda: {"queries": 0, "sessions": 0, "latencies": []})
    for fname in os.listdir(logs_dir):
        if not fname.endswith(".jsonl") or not fname.startswith("session_"):
            continue
        try:
            date_str = fname.replace("session_", "").replace(".jsonl", "")
            file_date = datetime.strptime(date_str[:8], "%Y%m%d").date()
        except (ValueError, IndexError):
            continue
        fpath = os.path.join(logs_dir, fname)
        try:
            daily[str(file_date)]["sessions"] += 1
            with open(fpath, encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("role") == "user":
                        daily[str(file_date)]["queries"] += 1
                    elapsed = entry.get("elapsed_sec")
                    if elapsed is not None:
                        daily[str(file_date)]["latencies"].append(elapsed)
        except (json.JSONDecodeError, OSError):
            pass
    result = []
    for date_str in sorted(daily.keys()):
        d = daily[date_str]
        latencies = d["latencies"]
        result.append({
            "date": date_str,
            "queries": d["queries"],
            "sessions": d["sessions"],
            "avg_latency": round(sum(latencies) / len(latencies), 2) if latencies else 0,
        })
    return result[-days:]


def check_alerts(cfg) -> list[dict]:
    alerts = []
    try:
        from legacy_winsarp.core.rag_engine import check_ollama_uncached as check_ollama
        ok, msg = check_ollama(cfg.DEFAULT_MODEL_ID)
        if not ok:
            alerts.append({"level": "critical", "message": f"Ollama non disponibile: {msg}", "metric": "ollama"})
    except Exception:
        pass
    disk = shutil.disk_usage(cfg.BASE_DIR)
    free_gb = disk.free / (1024**3)
    if free_gb < 1.0:
        alerts.append({"level": "critical", "message": f"Spazio disco basso: {free_gb:.1f}GB libero", "metric": "disk"})
    elif free_gb < 5.0:
        alerts.append({"level": "warning", "message": f"Spazio disco in esaurimento: {free_gb:.1f}GB libero", "metric": "disk"})
    if not os.path.exists(cfg.CHROMA_DIR):
        alerts.append({"level": "warning", "message": "ChromaDB directory non trovata", "metric": "chroma"})
    if not os.path.exists(cfg.LOGS_DIR):
        alerts.append({"level": "info", "message": "Directory logs non esistente", "metric": "logs"})
    return alerts

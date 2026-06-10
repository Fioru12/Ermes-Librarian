"""
monitor_dashboard.py
Dashboard di monitoring e KPI per Ermes.
Fornisce metriche su:
- Utilizzo del sistema (sessioni, query, utenti)
- Performance (tempi di risposta, token utilizzati)
- Stato infrastruttura (Ollama, ChromaDB, documenti)
- Feedback utenti (risposte utili/non utili)

Usabile come modulo standalone o integrato nell'app.
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

# ============================================================
# METRICHE DI SISTEMA
# ============================================================

def count_sessions(logs_dir: str, days: int = 7) -> dict:
    """
    Conta le sessioni di conversazione nei log.

    Returns:
        dict con total_sessions, sessions_today, sessions_week
    """
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

    return {
        "total_sessions": total,
        "sessions_today": today_count,
        "sessions_week": week_count,
    }


def count_queries(logs_dir: str, days: int = 7) -> dict:
    """
    Analizza i log delle sessioni per contare le query.

    Returns:
        dict con total_queries, queries_today, queries_by_module
    """
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

    return {
        "total_queries": total,
        "queries_today": today_count,
        "queries_by_module": dict(queries_by_module),
    }


def analyze_performance(logs_dir: str, days: int = 7) -> dict:
    """
    Analizza i tempi di risposta dalle sessioni log.

    Returns:
        dict con avg_response_time, max_response_time, min_response_time,
        response_times_by_hour
    """
    if not os.path.exists(logs_dir):
        return {
            "avg_response_time_s": 0,
            "max_response_time_s": 0,
            "min_response_time_s": 0,
            "total_responses": 0,
        }

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
        return {
            "avg_response_time_s": 0,
            "max_response_time_s": 0,
            "min_response_time_s": 0,
            "total_responses": 0,
        }

    return {
        "avg_response_time_s": round(sum(times) / len(times), 2),
        "max_response_time_s": round(max(times), 2),
        "min_response_time_s": round(min(times), 2),
        "total_responses": len(times),
    }


def analyze_audit(audit_file: str, days: int = 30) -> dict:
    """
    Analizza il log audit per monitoraggio attività admin.

    Returns:
        dict con azioni totali, azioni per tipo, utenti più attivi
    """
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

    return {
        "total_actions": total,
        "actions_by_type": dict(actions_by_type),
        "top_users": [{"username": u, "actions": c} for u, c in top_users],
    }


def check_infrastructure_status(cfg) -> dict:
    """
    Verifica lo stato dell'infrastruttura.

    Returns:
        dict con stato di: documenti, chroma, logs, security
    """
    status = {}

    # Documenti
    if os.path.exists(cfg.DOCS_DIR):
        moduli = [
            d for d in os.listdir(cfg.DOCS_DIR)
            if os.path.isdir(os.path.join(cfg.DOCS_DIR, d))
        ]
        total_files = sum(
            len([
                f for f in os.listdir(os.path.join(cfg.DOCS_DIR, m))
                if os.path.isfile(os.path.join(cfg.DOCS_DIR, m, f))
            ])
            for m in moduli
        )
        status["documents"] = {
            "modules": len(moduli),
            "module_names": moduli,
            "total_files": total_files,
        }
    else:
        status["documents"] = {"modules": 0, "module_names": [], "total_files": 0}

    # ChromaDB
    if os.path.exists(cfg.CHROMA_DIR):
        chroma_dirs = [
            d for d in os.listdir(cfg.CHROMA_DIR)
            if os.path.isdir(os.path.join(cfg.CHROMA_DIR, d))
        ]
        status["chroma"] = {"collections": len(chroma_dirs), "names": chroma_dirs}
    else:
        status["chroma"] = {"collections": 0, "names": []}

    # Log
    if os.path.exists(cfg.LOGS_DIR):
        session_logs = len([
            f for f in os.listdir(cfg.LOGS_DIR)
            if f.endswith(".jsonl") and f.startswith("session_")
        ])
        has_audit = os.path.exists(cfg.AUDIT_FILE)
        status["logs"] = {"sessions": session_logs, "has_audit": has_audit}
    else:
        status["logs"] = {"sessions": 0, "has_audit": False}

    # Security
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

    # Spazio disco approssimativo
    total_size = 0
    for path, label in [
        (cfg.DOCS_DIR, "documenti"),
        (cfg.CHROMA_DIR, "chroma_db"),
        (cfg.LOGS_DIR, "logs"),
    ]:
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


def get_feedback_stats(session_state) -> dict:
    """
    Analizza i feedback registrati nella sessione corrente.

    Returns:
        dict con up_count, down_count, total
    """
    up_count = 0
    down_count = 0

    for key, value in session_state.items():
        if key.startswith("feedback_"):
            if value == "up":
                up_count += 1
            elif value == "down":
                down_count += 1

    return {
        "up_votes": up_count,
        "down_votes": down_count,
        "total": up_count + down_count,
    }


def generate_full_report(cfg) -> dict:
    """
    Genera un report completo di tutte le metriche.
    """
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
    """Esporta il report delle metriche in JSON."""
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)


def get_daily_trends(logs_dir: str, days: int = 7) -> list[dict]:
    """
    Restituisce trend giornalieri di query e sessioni.
    
    Returns:
        List di dict: [{"date": "2026-06-10", "queries": 15, "sessions": 3, "avg_latency": 12.5}, ...]
    """
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
    """
    Controlla soglie di alerting e restituisce alert attivi.
    
    Returns:
        List di dict: [{"level": "warning", "message": "...", "metric": "..."}, ...]
    """
    alerts = []
    
    # 1. Ollama status
    try:
        from core.rag_engine import check_ollama_uncached as check_ollama
        ok, msg = check_ollama(cfg.DEFAULT_MODEL_ID)
        if not ok:
            alerts.append({
                "level": "critical",
                "message": f"Ollama non disponibile: {msg}",
                "metric": "ollama",
            })
    except Exception:
        pass

    # 2. Disk space
    import shutil
    disk = shutil.disk_usage(cfg.BASE_DIR)
    free_gb = disk.free / (1024**3)
    if free_gb < 1.0:
        alerts.append({
            "level": "critical",
            "message": f"Spazio disco basso: {free_gb:.1f}GB libero",
            "metric": "disk",
        })
    elif free_gb < 5.0:
        alerts.append({
            "level": "warning",
            "message": f"Spazio disco in esaurimento: {free_gb:.1f}GB libero",
            "metric": "disk",
        })

    # 3. ChromaDB
    if not os.path.exists(cfg.CHROMA_DIR):
        alerts.append({
            "level": "warning",
            "message": "ChromaDB directory non trovata",
            "metric": "chroma",
        })

    # 4. Log directory
    if not os.path.exists(cfg.LOGS_DIR):
        alerts.append({
            "level": "info",
            "message": "Directory logs non esistente",
            "metric": "logs",
        })

    return alerts


def render_dashboard_in_sidebar(cfg, session_state, modulo_scelto: str = None):
    """
    Renderizza un mini-dashboard KPI nella sidebar.
    Da chiamare all'interno del blocco `with st.sidebar:`.
    """
    import streamlit as st

    with st.expander("📊 Dashboard KPI", expanded=False):
        # Alert banner
        alerts = check_alerts(cfg)
        critical = [a for a in alerts if a["level"] == "critical"]
        warnings = [a for a in alerts if a["level"] == "warning"]
        if critical:
            for a in critical:
                st.error(f"🚨 {a['message']}")
        if warnings:
            for a in warnings:
                st.warning(f"⚠️ {a['message']}")

        # Metriche veloci
        sess = count_sessions(cfg.LOGS_DIR)
        qry = count_queries(cfg.LOGS_DIR)
        perf = analyze_performance(cfg.LOGS_DIR)
        fb = get_feedback_stats(session_state)

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Sessioni (7gg)", sess.get("sessions_week", 0))
        with col2:
            st.metric("Query (7gg)", qry.get("total_queries", 0))

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Tempo medio", f"{perf.get('avg_response_time_s', 0):.1f}s")
        with col2:
            st.metric("Risposte totali", perf.get("total_responses", 0))

        # Feedback
        if fb["total"] > 0:
            up_pct = round(fb["up_votes"] / fb["total"] * 100) if fb["total"] > 0 else 0
            st.progress(up_pct / 100, text=f"👍 Utili: {up_pct}% ({fb['up_votes']}/{fb['total']})")
        else:
            st.caption("Nessun feedback ancora registrato")

        # Knowledge Graph stats
        try:
            from core.knowledge_graph import KnowledgeGraph
            kg = KnowledgeGraph()
            n_formule = len(kg._nodes)
            n_tipi = len(set(n.get("tipo", "") for n in kg._nodes.values() if n.get("tipo")))
            st.caption(f"🔗 Knowledge Graph: {n_formule} formule, {n_tipi} tipi")
        except Exception:
            pass

        # Evaluation scores (if available)
        eval_path = os.path.join(cfg.BASE_DIR, "evaluation", "results_hybrid.json")
        if os.path.exists(eval_path):
            try:
                with open(eval_path, encoding="utf-8") as f:
                    eval_data = json.load(f)
                summary = eval_data.get("summary", {})
                pass_rate = summary.get("pass_rate_pct", 0)
                avg_kw = summary.get("avg_keyword_score", 0)
                total_eval = summary.get("total_queries", 0)
                if total_eval > 0:
                    st.caption(f"📈 Eval: {pass_rate:.0f}% pass ({total_eval} query, kw={avg_kw:.2f})")
            except (json.JSONDecodeError, OSError):
                pass

        # Current model
        model_id = session_state.get("model_id", cfg.DEFAULT_MODEL_ID)
        st.caption(f"🤖 Modello: {model_id}")

        # Stato infratruttura
        infra = check_infrastructure_status(cfg)
        st.caption(
            f"📁 {infra['documents']['total_files']} file in "
            f"{infra['documents']['modules']} moduli"
        )
        st.caption(f"💾 {infra['disk_usage_mb']} MB su disco")

        # Daily trend mini-chart
        trends = get_daily_trends(cfg.LOGS_DIR, days=7)
        if trends:
            with st.container():
                st.caption("📉 Trend 7 giorni")
                dates = [t["date"][-5:] for t in trends]  # MM-DD
                queries = [t["queries"] for t in trends]
                # Mini sparkline using bar chart
                chart_data = dict(zip(dates, queries))
                st.bar_chart(chart_data, height=100)

        # Alert summary
        if alerts:
            n_critical = len([a for a in alerts if a["level"] == "critical"])
            n_warn = len([a for a in alerts if a["level"] == "warning"])
            if n_critical or n_warn:
                st.caption(f"🚨 {n_critical} critici, ⚠️ {n_warn} warning")

        # Link a report completo
        if st.button("📊 Report completo", use_container_width=True):
            report = generate_full_report(cfg)
            export_report_to_json(report)
            st.toast("Report salvato in logs/dashboard_report.json", icon="✅")
            report_json = json.dumps(report, indent=2, ensure_ascii=False)
            st.download_button(
                "📥 Scarica report",
                report_json,
                f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                use_container_width=True,
            )

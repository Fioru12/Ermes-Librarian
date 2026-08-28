"""
monitoring.py
Metriche di audit per Ermes.
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta


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
                # Per riga, non sull'intero ciclo: allineato a come api/audit.py
                # legge lo stesso file altrove. Un try/except attorno all'intero
                # for interrompeva silenziosamente la lettura alla prima riga
                # corrotta, azzerando le statistiche di ogni riga successiva
                # anche se valida — mentre /api/audit/logs sullo stesso file
                # avrebbe continuato a funzionare normalmente.
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
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
    except OSError:
        pass
    top_users = sorted(users_count.items(), key=lambda x: x[1], reverse=True)[:5]
    return {"total_actions": total, "actions_by_type": dict(actions_by_type), "top_users": [{"username": u, "actions": c} for u, c in top_users]}

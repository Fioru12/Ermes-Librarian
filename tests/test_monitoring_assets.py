"""Il profilo di monitoraggio opzionale deve restare coerente con il codice.

Una regola di alert che cita una metrica rinominata o rimossa non dà errore:
semplicemente non scatta mai. Questo test lo rende un errore di build.
"""

import json
import re
from pathlib import Path

import yaml

RADICE = Path(__file__).resolve().parent.parent
MONITORING = RADICE / "deploy" / "monitoring"


def _metriche_esposte() -> set[str]:
    """Nomi delle metriche definite in core/metrics.py (con i suffissi di Prometheus)."""
    sorgente = (RADICE / "core" / "metrics.py").read_text(encoding="utf-8")
    nomi = set(re.findall(r'"(ermes_[a-z_]+)"', sorgente))
    esposte = set(nomi)
    for nome in nomi:
        esposte |= {f"{nome}_bucket", f"{nome}_count", f"{nome}_sum"}
    return esposte


def _metriche_citate(testo: str) -> set[str]:
    return set(re.findall(r"\bermes_[a-z_]+\b", testo))


def test_every_alert_rule_uses_a_metric_that_exists():
    regole = yaml.safe_load((MONITORING / "alerts.yml").read_text(encoding="utf-8"))
    esposte = _metriche_esposte()

    espressioni = [r["expr"] for g in regole["groups"] for r in g["rules"]]
    assert espressioni, "alerts.yml non contiene regole"
    for expr in espressioni:
        mancanti = _metriche_citate(expr) - esposte
        assert not mancanti, f"la regola cita metriche inesistenti: {sorted(mancanti)}"


def test_the_dashboard_uses_only_metrics_that_exist():
    dashboard = json.loads((MONITORING / "grafana-dashboard.json").read_text(encoding="utf-8"))
    esposte = _metriche_esposte()

    citate: set[str] = set()
    for pannello in dashboard.get("panels", []):
        for target in pannello.get("targets", []):
            citate |= _metriche_citate(target.get("expr", ""))
    mancanti = citate - esposte
    assert not mancanti, f"la dashboard cita metriche inesistenti: {sorted(mancanti)}"


def test_every_alert_has_severity_and_an_explanation():
    regole = yaml.safe_load((MONITORING / "alerts.yml").read_text(encoding="utf-8"))
    for gruppo in regole["groups"]:
        for regola in gruppo["rules"]:
            assert regola["labels"]["severity"] in {"critical", "warning", "info"}, regola["alert"]
            assert regola["annotations"]["summary"], regola["alert"]


def test_the_monitoring_files_are_valid_yaml_and_wired_together():
    prometheus = yaml.safe_load((MONITORING / "prometheus.yml").read_text(encoding="utf-8"))
    assert prometheus["rule_files"] == ["/etc/prometheus/alerts.yml"]
    # /metrics fuori dal loopback richiede il token: lo scrape deve mandarlo.
    assert prometheus["scrape_configs"][0]["authorization"]["credentials_file"]

    alertmanager = yaml.safe_load((MONITORING / "alertmanager.yml").read_text(encoding="utf-8"))
    assert alertmanager["receivers"][0]["webhook_configs"][0]["url_file"]

    compose = yaml.safe_load((RADICE / "docker-compose.monitoring.yml").read_text(encoding="utf-8"))
    assert {"prometheus", "alertmanager", "grafana"} <= set(compose["services"])
    for nome in ("prometheus", "alertmanager", "grafana"):
        for porta in compose["services"][nome]["ports"]:
            # Strumenti di amministrazione: solo sul loopback, mai sulla rete.
            assert porta.startswith("127.0.0.1:"), f"{nome} espone {porta} su tutte le interfacce"


def test_no_default_secret_in_the_monitoring_profile():
    """Token e password devono essere obbligatori, senza un valore noto di ripiego."""
    testo = (RADICE / "docker-compose.monitoring.yml").read_text(encoding="utf-8")
    assert "${ERMES_METRICS_TOKEN:?" in testo
    assert "${GRAFANA_ADMIN_PASSWORD:?" in testo
    assert not re.search(r"ADMIN_PASSWORD=\$\{[A-Z_]+:-", testo), "password di Grafana con default"


def test_slack_teams_example_is_valid_and_keeps_secrets_out_of_the_yaml():
    """L'esempio per Slack/Teams deve restare leggibile e non contenere indirizzi di webhook."""
    import pathlib

    import yaml

    path = pathlib.Path(__file__).resolve().parent.parent / "deploy" / "monitoring" / "alertmanager.slack-teams.example.yml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    receiver = config["receivers"][0]
    assert receiver["slack_configs"][0]["api_url_file"]
    assert receiver["msteamsv2_configs"][0]["webhook_url_file"]
    codice = [r for r in path.read_text(encoding="utf-8").splitlines() if not r.lstrip().startswith("#")]
    assert not any("https://" in riga for riga in codice), "un indirizzo di webhook e' finito nel YAML"


def test_the_dashboard_follows_the_chosen_period_and_never_draws_through_gaps():
    """I numeri in alto valgono per il periodo scelto (non "dall'ultimo riavvio", che azzerava tutto
    a ogni restart) e i grafici non uniscono i vuoti con una linea, come se ci fossero misure."""
    dashboard = json.loads((MONITORING / "grafana-dashboard.json").read_text(encoding="utf-8"))
    pannelli = []

    def raccogli(elenco):
        for p in elenco:
            pannelli.append(p)
            raccogli(p.get("panels", []))

    raccogli(dashboard.get("panels", []))
    for p in pannelli:
        if p.get("type") == "stat":
            for t in p.get("targets", []):
                assert "$__range" in t.get("expr", ""), f"{p['title']}: deve contare nel periodo scelto"
        custom = p.get("fieldConfig", {}).get("defaults", {}).get("custom", {})
        assert custom.get("spanNulls") is not True, f"{p.get('title')}: unisce i vuoti"


def test_a_percent_panel_is_scaled_to_percent():
    """Un pannello con unita' "percent" mostra 0-100: un rapporto 0-1 va moltiplicato per 100.
    Riscrivendo la formula del tasso di astensione il "* 100" era andato perso (mostrava 0,44%)."""
    dashboard = json.loads((MONITORING / "grafana-dashboard.json").read_text(encoding="utf-8"))
    for p in dashboard.get("panels", []):
        if p.get("fieldConfig", {}).get("defaults", {}).get("unit") == "percent":
            for t in p.get("targets", []):
                expr = t.get("expr", "")
                if " / " in expr:
                    assert expr.rstrip().endswith("* 100"), f"{p['title']}: rapporto non scalato a percentuale"

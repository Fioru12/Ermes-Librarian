"""ermes_system_info deve dire quale versione gira, non "unknown"."""

from fastapi.testclient import TestClient

import api


def test_the_system_info_metric_carries_the_application_version():
    with TestClient(api.app):  # esegue il lifespan, che inizializza la metrica
        from core.metrics import expose

        testo = expose()
    riga = next(linea for linea in testo.splitlines() if linea.startswith("ermes_system_info{"))
    assert f'version="{api.app.version}"' in riga
    assert 'version="unknown"' not in riga

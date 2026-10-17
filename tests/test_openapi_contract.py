"""Il contratto OpenAPI deve essere generabile senza ambiguita'.

FastAPI avvisa (UserWarning) quando due operazioni hanno lo stesso operationId:
un client generato dallo schema non sa piu' quale funzione corrisponde a quale
chiamata. Succedeva con `api_route(methods=["GET", "POST"])` sul webhook di
Microsoft Graph. Qui l'avviso diventa un errore.
"""

import warnings

from api import app


def test_every_operation_has_a_unique_operation_id():
    app.openapi_schema = None  # forza la rigenerazione, altrimenti l'avviso e' gia' passato
    with warnings.catch_warnings(record=True) as raccolti:
        warnings.simplefilter("always")
        schema = app.openapi()
    duplicati = [str(w.message) for w in raccolti if "Duplicate Operation ID" in str(w.message)]
    assert not duplicati, duplicati

    ids = [op["operationId"] for path in schema["paths"].values() for op in path.values() if "operationId" in op]
    assert len(ids) == len(set(ids))


def test_the_graph_webhook_answers_both_methods_with_distinct_operations():
    schema = app.openapi()
    percorso = schema["paths"]["/api/connectors/webhooks/microsoft-graph"]
    assert {"get", "post"} <= set(percorso)
    assert percorso["get"]["operationId"] != percorso["post"]["operationId"]

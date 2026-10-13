"""Registro dei tipi di connettore.

Prima i tipi erano una catena di `if` in api/connectors.py, ripetuta in una
regex di validazione: aggiungere un connettore voleva dire modificare Ermes
in due punti. Ora ogni tipo e' registrato qui con `register_connector()`.

Connettori esterni
------------------
Un'azienda puo' fornire i propri connettori senza toccare questo repository:
un modulo Python importabile che chiama `register_connector()` all'import,
elencato in `ERMES_CONNECTOR_PLUGINS` (moduli separati da virgola).

Si caricano solo i moduli elencati, non tutto cio' che e' installato (niente
entry point automatici): importare un modulo esegue il suo codice con i
permessi di Ermes, e questa deve essere una decisione esplicita di chi
amministra l'installazione, non un effetto collaterale di un `pip install`.
Un plugin che non si importa o non registra niente fa fallire la prima
richiesta ai connettori con un errore chiaro, invece di sparire in silenzio.
"""

from __future__ import annotations

import importlib
import logging
import re
import threading

import config
from core.connectors.base import BaseConnector
from core.connectors.confluence import ConfluenceConnector
from core.connectors.google_drive import GoogleDriveConnector
from core.connectors.local_folder import LocalFolderConnector
from core.connectors.microsoft_graph import MicrosoftGraphConnector
from core.connectors.s3_bucket import S3BucketConnector
from core.connectors.web_scraper import WebScraperConnector
from core.connectors.webdav import WebDAVConnector

_logger = logging.getLogger(__name__)

_TYPE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,63}$")

_BUILTIN: dict[str, type[BaseConnector]] = {
    "microsoft_graph": MicrosoftGraphConnector,
    "google_drive": GoogleDriveConnector,
    "confluence": ConfluenceConnector,
    "web_scraper": WebScraperConnector,
    "local_folder": LocalFolderConnector,
    "s3_bucket": S3BucketConnector,
    "webdav": WebDAVConnector,
}

_registry: dict[str, type[BaseConnector]] = dict(_BUILTIN)
_loaded_plugins: set[str] = set()
_lock = threading.RLock()


class ConnectorPluginError(RuntimeError):
    """Un plugin elencato in ERMES_CONNECTOR_PLUGINS non e' utilizzabile."""


def register_connector(type_name: str, connector_class: type[BaseConnector]) -> None:
    """Registra un tipo di connettore. Da chiamare all'import del modulo plugin."""
    if not _TYPE_NAME.match(type_name):
        raise ValueError(f"Nome di tipo connettore non valido: {type_name!r} (atteso [a-z][a-z0-9_]*)")
    if not (isinstance(connector_class, type) and issubclass(connector_class, BaseConnector)):
        raise TypeError(f"{connector_class!r} non estende BaseConnector")
    with _lock:
        existing = _registry.get(type_name)
        if existing is not None and existing is not connector_class:
            # Sostituire in silenzio un connettore integrato (es. local_folder,
            # che ha controlli sui percorsi) con codice esterno e' esattamente
            # cio' che non deve poter succedere per sbaglio.
            raise ValueError(f"Tipo connettore gia' registrato: {type_name!r}")
        _registry[type_name] = connector_class


def _configured_plugins() -> list[str]:
    raw = config.cfg.CONNECTOR_PLUGINS
    return [name.strip() for name in raw.split(",") if name.strip()]


def _ensure_plugins_loaded() -> None:
    with _lock:
        for module_name in _configured_plugins():
            if module_name in _loaded_plugins:
                continue
            before = set(_registry)
            try:
                importlib.import_module(module_name)
            except Exception as errore:
                raise ConnectorPluginError(
                    f"Plugin connettore {module_name!r} non importabile: {errore}"
                ) from errore
            if set(_registry) == before:
                raise ConnectorPluginError(
                    f"Il plugin {module_name!r} non ha registrato alcun connettore (manca register_connector?)"
                )
            _loaded_plugins.add(module_name)
            _logger.info("Plugin connettore caricato: %s -> %s", module_name, sorted(set(_registry) - before))


def available_types() -> list[str]:
    _ensure_plugins_loaded()
    with _lock:
        return sorted(_registry)


def is_builtin(type_name: str) -> bool:
    return type_name in _BUILTIN


def create_connector(type_name: str, connector_config: dict) -> BaseConnector:
    """Istanzia il connettore; KeyError se il tipo non e' registrato."""
    _ensure_plugins_loaded()
    with _lock:
        connector_class = _registry[type_name]
    return connector_class(connector_config)


def _reset_for_tests() -> None:
    with _lock:
        _registry.clear()
        _registry.update(_BUILTIN)
        _loaded_plugins.clear()

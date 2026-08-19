"""
modules/__init__.py
Sistema di moduli configurabili per Ermes.
Ogni modulo ha le sue regole specifiche: prompt, parser, validatore.
"""
import importlib
import os
import pkgutil

from .base import BaseModule


def discover_modules() -> dict[str, BaseModule]:
    """
    Scopre automaticamente tutti i moduli disponibili nella cartella modules/.
    Ogni file .py (esclusi __init__.py e base.py) viene importato; se contiene
    una sottoclasse concreta di BaseModule, viene istanziata e registrata.

    Returns:
        dict[str, BaseModule]: Mappa nome_modulo → istanza del modulo.
    """
    discovered: dict[str, BaseModule] = {}
    pkg_path = os.path.dirname(__file__)

    for importer, modname, is_pkg in pkgutil.iter_modules([pkg_path]):
        if modname in ("__init__", "base"):
            continue
        try:
            mod = importlib.import_module(f".{modname}", __package__)
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if isinstance(attr, type) and issubclass(attr, BaseModule) and attr is not BaseModule:
                    instance = attr()
                    discovered[instance.name] = instance
        except Exception:
            pass

    return discovered

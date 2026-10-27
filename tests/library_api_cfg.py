"""Dove patchare `cfg` per gli endpoint delle biblioteche.

`api.libraries` e' un package: ogni sottomodulo importa `cfg` per conto suo,
quindi un test che cambia la configurazione deve sostituirla in tutti. Elenco
calcolato, non scritto a mano: un sottomodulo nuovo non resta col cfg vero.
"""

import importlib
import pkgutil

import api.libraries

LIBRARIES_CFG_TARGETS = tuple(
    f"{info.name}.cfg"
    for info in pkgutil.iter_modules(api.libraries.__path__, "api.libraries.")
    if hasattr(importlib.import_module(info.name), "cfg")
)

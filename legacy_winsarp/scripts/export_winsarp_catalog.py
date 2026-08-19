"""Esporta il catalogo WinSarp in JSON strutturato.

Uso:
    .venv\\Scripts\\python.exe scripts\\export_winsarp_catalog.py

Output:
    data/winsarp_catalog.json
"""

from __future__ import annotations

import json
from pathlib import Path

from pathlib import Path
from config import cfg
from legacy_winsarp.core.winsarp.catalog import save_catalog_json


def main() -> None:
    catalog = save_catalog_json(Path(cfg.CATALOGO_JSON_PATH), Path(cfg.CATALOGO_PATH))
    print(json.dumps(
        {
            "source": str(cfg.CATALOGO_PATH),
            "output": str(cfg.CATALOGO_JSON_PATH),
            "count": len(catalog),
            "first_ids": [item["id"] for item in catalog[:10]],
        },
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()

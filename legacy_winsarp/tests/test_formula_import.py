import os
import pytest
import shutil
import tempfile
import importlib
import config
from pathlib import Path

# ── Backup real catalog files before test ──
_REAL_DOCS = Path(__file__).parent.parent / "documenti" / "WinSarp" / "WinSarp_Formule.txt"
_REAL_JSON = Path(__file__).parent.parent / "data" / "winsarp_catalog.json"
_REAL_KG = Path(__file__).parent.parent / "data" / "winsarp_graph.json"

_BACKUP_DIR = Path(tempfile.mkdtemp(prefix="ermes_catalog_backup_"))

def _backup_real():
    _BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    for src in [_REAL_DOCS, _REAL_JSON]:
        if src.exists():
            shutil.copy2(src, _BACKUP_DIR / src.name)

def _restore_real():
    for src in [_REAL_DOCS, _REAL_JSON]:
        bak = _BACKUP_DIR / src.name
        if bak.exists():
            shutil.copy2(bak, src)
    if _BACKUP_DIR.exists():
        shutil.rmtree(_BACKUP_DIR, ignore_errors=True)
    if Path(BASE_TEMP).exists():
        shutil.rmtree(BASE_TEMP, ignore_errors=True)

# Backup real catalog at module load time, restore at process exit
_backup_real()
import atexit
atexit.register(_restore_real)

# ── Setup temp environment BEFORE importing api ──
BASE_TEMP = tempfile.mkdtemp(prefix="ermes_import_test_")
os.environ["ERMES_API_KEY"] = "e2e-super-admin-key-12345"
os.environ["ERMES_BASE_DIR"] = BASE_TEMP
os.environ["ERMES_ENABLE_FORMULA_GENERATION"] = "1"
importlib.reload(config)

from fastapi.testclient import TestClient
from api import app
from contextlib import asynccontextmanager

# Override lifespan
@asynccontextmanager
async def noop_lifespan(_app):
    yield
app.router.lifespan_context = noop_lifespan

# Create required subdirectories
for sub in ["logs", "security", "chroma_db", "data", "documenti/WinSarp"]:
    os.makedirs(os.path.join(BASE_TEMP, sub), exist_ok=True)

@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

def test_formula_import_success(client):
    admin_headers = {"Authorization": "Bearer e2e-super-admin-key-12345"}
    
    # 1. Define custom workbook markdown
    custom_workbook = """
## [999](#999) | Test Formula | Inizio Giornata | Standard |
**Tipo:** Inizio Giornata  
**Scopo:** Test formula importata.
```
(!999);
```
---
"""
    
    # 2. Upload workbook
    files = {"file": ("custom_workbook.md", custom_workbook, "text/markdown")}
    resp = client.post("/api/formula/import", files=files, headers=admin_headers)
    
    assert resp.status_code == 200, f"Import failed: {resp.json()}"
    data = resp.json()
    assert data["success"] is True
    assert data["formulas_imported"] == 1
    assert 999 in data["formula_ids"]
    assert data["graph_nodes"] > 0

def test_formula_import_invalid_file(client):
    admin_headers = {"Authorization": "Bearer e2e-super-admin-key-12345"}
    
    # Invalid file extension
    files = {"file": ("invalid.pdf", "some content", "application/pdf")}
    resp = client.post("/api/formula/import", files=files, headers=admin_headers)
    
    assert resp.status_code == 400

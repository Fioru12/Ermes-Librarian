from pathlib import Path

from config import cfg


def test_legacy_docs_dir_and_library_storage_dir_never_overlap():
    """DOCS_DIR (legacy WinSarp module folders, no per-document ACL) and
    LIBRARY_STORAGE_DIR (new library originals, ACL-checked before serving)
    must stay on disjoint subtrees. If they ever collided, the legacy
    module-based endpoint could read library-owned files by path, bypassing
    the library ACL — see docs/AUDIT_2026-08-19.md."""
    docs_dir = Path(cfg.DOCS_DIR).resolve()
    library_dir = Path(cfg.LIBRARY_STORAGE_DIR).resolve()

    assert docs_dir != library_dir
    assert library_dir not in docs_dir.parents
    assert docs_dir not in library_dir.parents

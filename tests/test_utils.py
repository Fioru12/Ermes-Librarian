import json

from core.utils import compute_dir_hash, docs_changed, save_hash


def test_compute_dir_hash_changes_when_file_changes(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("one", encoding="utf-8")
    h1 = compute_dir_hash(str(tmp_path))

    f.write_text("two", encoding="utf-8")
    h2 = compute_dir_hash(str(tmp_path))

    assert h1 != h2


def test_docs_changed_false_when_hash_matches(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "x.txt").write_text("abc", encoding="utf-8")

    hash_file = tmp_path / "hashes.json"
    current = compute_dir_hash(str(docs_dir))
    save_hash(str(hash_file), "WinSarp", current)

    assert docs_changed(str(hash_file), "WinSarp", str(docs_dir)) is False


def test_docs_changed_true_when_new_module_has_files(tmp_path):
    docs_dir = tmp_path / "docs2"
    docs_dir.mkdir()
    (docs_dir / "x.txt").write_text("abc", encoding="utf-8")

    hash_file = tmp_path / "hashes.json"
    hash_file.write_text(json.dumps({}), encoding="utf-8")

    assert docs_changed(str(hash_file), "ModuloNuovo", str(docs_dir)) is True

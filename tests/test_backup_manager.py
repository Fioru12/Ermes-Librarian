import os
import tarfile
import threading
import types


from core import backup_manager as bm


def _fake_cfg(base_dir):
    """A minimal stand-in for the frozen Config singleton, exposing only
    the attributes backup_manager.py actually reads. Using this instead of
    monkeypatching the real cfg's fields avoids fighting its frozen
    dataclass __setattr__ and, more importantly, avoids the cross-test
    global-state leak documented in tests/test_e2e_api.py — this fake is
    local to each test and never shared."""
    return types.SimpleNamespace(
        BASE_DIR=base_dir,
        CHROMA_DIR=os.path.join(base_dir, "chroma_db"),
        LOGS_DIR=os.path.join(base_dir, "logs"),
    )


class TestGetBackupPath:
    def test_creates_directory(self, temp_dir, monkeypatch):
        backup_dir = os.path.join(temp_dir, "backups_test")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        result = bm._get_backup_path()
        assert os.path.exists(backup_dir)
        assert result == backup_dir


class TestCreateBackup:
    def test_creates_tar_gz(self, temp_dir, monkeypatch):
        backup_dir = os.path.join(temp_dir, "backups")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        result = bm.create_backup(label="test")
        assert os.path.exists(result["path"])
        assert "test" in result["name"]
        # size_mb e' arrotondato a due decimali: un backup piccolo vale 0.0 e
        # l'asserzione falliva su un checkout pulito (CI) pur passando in
        # locale, dove BASE_DIR contiene molto piu' materiale. Il fatto da
        # verificare e' che l'archivio non sia vuoto, quindi si controllano i byte.
        assert os.path.getsize(result["path"]) > 0
        assert result["size_mb"] >= 0
        with tarfile.open(result["path"], "r:gz") as tar:
            names = tar.getnames()
            assert len(names) > 0

    def test_backup_without_label(self, temp_dir, monkeypatch):
        backup_dir = os.path.join(temp_dir, "backups")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        result = bm.create_backup()
        assert os.path.exists(result["path"])

    def test_backup_creates_under_backup_dir(self, temp_dir, monkeypatch):
        backup_dir = os.path.join(temp_dir, "backups")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        result = bm.create_backup()
        assert result["path"].startswith(backup_dir)


class TestCleanupOldBackups:
    def test_keeps_only_last_n(self, temp_dir, monkeypatch):
        backup_dir = os.path.join(temp_dir, "backups")
        os.makedirs(backup_dir)
        for i in range(5):
            path = os.path.join(backup_dir, f"ermes_backup_20260625_000{i}.tar.gz")
            with open(path, "w") as f:
                f.write(f"backup-{i}")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        bm._cleanup_old_backups(keep=2)
        remaining = sorted(os.listdir(backup_dir))
        assert len(remaining) == 2

    def test_no_cleanup_when_under_limit(self, temp_dir, monkeypatch):
        backup_dir = os.path.join(temp_dir, "backups")
        os.makedirs(backup_dir)
        for i in range(3):
            path = os.path.join(backup_dir, f"ermes_backup_20260625_000{i}.tar.gz")
            with open(path, "w") as f:
                f.write(f"backup-{i}")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        bm._cleanup_old_backups(keep=10)
        remaining = os.listdir(backup_dir)
        assert len(remaining) == 3


class TestRestoreBackup:
    """Previously untested: create_backup()/restore_backup() are the pair
    that actually matters (a backup nobody has restored isn't verified),
    including the atomic tempfile+os.replace write path and the lock that
    is supposed to make both operations safe to call concurrently."""

    def _seed_backup(self, temp_dir, monkeypatch, label="restoretest"):
        source_dir = os.path.join(temp_dir, "source")
        os.makedirs(os.path.join(source_dir, "data"), exist_ok=True)
        os.makedirs(os.path.join(source_dir, "logs"), exist_ok=True)
        with open(os.path.join(source_dir, "data", "winsarp_graph.json"), "w") as f:
            f.write('{"nodes": []}')
        with open(os.path.join(source_dir, "logs", "app.jsonl"), "w") as f:
            f.write('{"event": "seed"}\n')

        backup_dir = os.path.join(temp_dir, "backups")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        monkeypatch.setattr(bm, "cfg", _fake_cfg(source_dir))
        result = bm.create_backup(label=label)
        return result["name"]

    def test_restore_raises_for_missing_backup(self, temp_dir, monkeypatch):
        monkeypatch.setattr(bm, "BACKUP_DIR", os.path.join(temp_dir, "backups"))
        try:
            bm.restore_backup("does-not-exist")
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("Expected FileNotFoundError for a missing backup")

    def test_dry_run_lists_without_writing(self, temp_dir, monkeypatch):
        backup_name = self._seed_backup(temp_dir, monkeypatch)
        restore_target = os.path.join(temp_dir, "restore_target")
        monkeypatch.setattr(bm, "cfg", _fake_cfg(restore_target))

        result = bm.restore_backup(backup_name, dry_run=True)

        assert result["dry_run"] is True
        assert "data/winsarp_graph.json" in result["restored"]
        # A dry run must not create the target directory at all.
        assert not os.path.exists(restore_target)

    def test_restore_writes_files_atomically_and_skips_metadata(self, temp_dir, monkeypatch):
        backup_name = self._seed_backup(temp_dir, monkeypatch)
        restore_target = os.path.join(temp_dir, "restore_target")
        monkeypatch.setattr(bm, "cfg", _fake_cfg(restore_target))

        result = bm.restore_backup(backup_name, dry_run=False)

        restored_graph = os.path.join(restore_target, "data", "winsarp_graph.json")
        assert os.path.isfile(restored_graph)
        with open(restored_graph) as f:
            assert f.read() == '{"nodes": []}'
        # backup_metadata.json is bookkeeping, not a file to restore onto disk.
        assert "backup_metadata.json" not in result["restored"]
        assert not os.path.exists(os.path.join(restore_target, "backup_metadata.json"))
        # No leftover .tmp files from the tempfile+os.replace atomic write.
        leftovers = [f for f in os.listdir(os.path.join(restore_target, "data")) if f.endswith(".tmp")]
        assert leftovers == []

    def test_restore_skips_a_non_regular_member_instead_of_crashing(self, temp_dir, monkeypatch):
        """tarfile.extractfile() returns None for a member that is neither a
        directory nor a regular file (symlink, device, fifo) — mypy caught
        this as a real gap: the restore loop only checked member.isdir(),
        so an archive with such an entry would raise AttributeError on
        `with None as src`. A backup this module creates never contains one
        (it only tars the app's own directories), but a hand-crafted or
        corrupted archive could; a legitimate member elsewhere in the same
        archive must still restore correctly.
        """
        backup_dir = os.path.join(temp_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        archive_path = os.path.join(backup_dir, "special.tar.gz")
        with tarfile.open(archive_path, "w:gz") as tar:
            # FIFOTYPE: extractfile() returns None for it without raising,
            # which is the exact case being guarded against. A dangling
            # symlink was tried first and turned out to raise KeyError
            # *inside* extractfile() itself instead — a different failure,
            # caught only by actually running this test against the
            # unpatched code before trusting it as a regression test.
            special = tarfile.TarInfo(name="data/broken_fifo")
            special.type = tarfile.FIFOTYPE
            tar.addfile(special)

            import io
            content = b'{"nodes": []}'
            info = tarfile.TarInfo(name="data/winsarp_graph.json")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

        restore_target = os.path.join(temp_dir, "restore_target")
        monkeypatch.setattr(bm, "cfg", _fake_cfg(restore_target))

        result = bm.restore_backup("special", dry_run=False)

        assert "data/broken_fifo" not in result["restored"]
        assert "data/winsarp_graph.json" in result["restored"]
        restored_graph = os.path.join(restore_target, "data", "winsarp_graph.json")
        with open(restored_graph) as f:
            assert f.read() == '{"nodes": []}'

    def test_concurrent_create_backup_calls_do_not_corrupt_each_other(self, temp_dir, monkeypatch):
        """_backup_lock exists specifically so two callers (e.g. the manual
        API endpoint and the background scheduler) can't interleave writes
        to the same process. Two threads calling create_backup at once
        should produce two distinct, individually valid archives, not one
        corrupted file."""
        source_dir = os.path.join(temp_dir, "source")
        os.makedirs(os.path.join(source_dir, "data"), exist_ok=True)
        with open(os.path.join(source_dir, "data", "winsarp_graph.json"), "w") as f:
            f.write('{"nodes": []}')
        backup_dir = os.path.join(temp_dir, "backups")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        monkeypatch.setattr(bm, "cfg", _fake_cfg(source_dir))

        results: list[dict] = []
        errors: list[Exception] = []

        def _run(label):
            try:
                results.append(bm.create_backup(label=label))
            except Exception as error:  # pragma: no cover - failure path surfaced via assert below
                errors.append(error)

        threads = [threading.Thread(target=_run, args=(f"concurrent{i}",)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"create_backup raised under concurrency: {errors}"
        assert len(results) == 2
        paths = {r["path"] for r in results}
        assert len(paths) == 2, "both threads must produce distinct archive files"
        for r in results:
            assert os.path.exists(r["path"])
            with tarfile.open(r["path"], "r:gz") as tar:
                assert len(tar.getnames()) > 0, "archive must not be empty/corrupted"


class TestGetBackupStatus:
    def test_reports_totals_and_latest(self, temp_dir, monkeypatch):
        source_dir = os.path.join(temp_dir, "source")
        os.makedirs(os.path.join(source_dir, "data"), exist_ok=True)
        with open(os.path.join(source_dir, "data", "winsarp_graph.json"), "w") as f:
            f.write('{"nodes": []}')
        backup_dir = os.path.join(temp_dir, "backups")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        monkeypatch.setattr(bm, "cfg", _fake_cfg(source_dir))

        bm.create_backup(label="one")
        bm.create_backup(label="two")

        status = bm.get_backup_status()
        assert status["total_backups"] == 2
        assert status["latest"] is not None
        # These fixture archives are a few hundred bytes — round(x, 2) of
        # that legitimately rounds to 0.0 MB, so assert the underlying
        # bytes exist rather than the rounded-to-two-decimals figure.
        assert status["total_size_mb"] >= 0
        assert sum(os.path.getsize(f["path"]) for f in bm.list_backups()) > 0
        assert status["backup_dir"] == backup_dir

    def test_empty_when_no_backups_exist(self, temp_dir, monkeypatch):
        backup_dir = os.path.join(temp_dir, "backups_empty")
        monkeypatch.setattr(bm, "BACKUP_DIR", backup_dir)
        os.makedirs(backup_dir)

        status = bm.get_backup_status()
        assert status["total_backups"] == 0
        assert status["latest"] is None
        assert status["total_size_mb"] == 0

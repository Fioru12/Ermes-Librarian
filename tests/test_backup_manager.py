import os
import tarfile


from core import backup_manager as bm


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
        assert result["size_mb"] > 0
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

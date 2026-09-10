"""Backup: dove finiscono, quanti restano, e dove scrive il ripristino.

Tre difetti distinti in `core/backup_manager.py`, tutti dello stesso tipo —
codice che funziona in isolamento e non e' collegato a cio' che lo governa.

1. `ERMES_BACKUP_DIR` non era letta da nessuno. Il modulo calcola
   `BACKUP_DIR = os.path.join(cfg.BASE_DIR, "backups")` al momento
   dell'import, e `cfg.BACKUP_DIR` esiste in `config/storage.py` senza che
   niente la consumi. Chi imposta la variabile per mandare i backup su un
   disco separato — cioe' il motivo per cui la variabile esiste — li ottiene
   accanto ai dati che dovrebbero proteggere. Un backup sullo stesso disco
   dell'originale non e' un backup.

2. `ERMES_BACKUP_RETENTION_COUNT` era ugualmente inerte: la conservazione
   restava fissa a `MAX_BACKUPS = 10`.

3. Il ripristino scriveva dove diceva l'archivio. `target = os.path.join(
   cfg.BASE_DIR, member.name)`: con un nome di membro assoluto `os.path.join`
   scarta del tutto la base, e con `../..` esce dalla cartella. E' la
   vulnerabilita' classica degli archivi tar, e qui non c'e' `extractall`,
   quindi il filtro di sicurezza di tarfile non si applica. Nemmeno serviva un
   archivio ostile: se `LIBRARY_DB_PATH` punta fuori da `BASE_DIR`, i nomi dei
   membri li calcola `os.path.relpath` e cominciano legittimamente per `../`.
   Anche il nome del backup arrivava non validato dal percorso della rotta.
"""

import contextlib
import os
import tarfile
from pathlib import Path

import pytest

import config
import core.backup_manager as backup_manager

PASSWORD = "StrongPassword!123"


@pytest.fixture
def istanza(tmp_path, monkeypatch):
    """Isola BASE_DIR e la cartella dei backup, qualunque delle due versioni
    del modulo sia in prova."""
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    dischi = tmp_path / "nas"
    dischi.mkdir()
    test_cfg = config.cfg.replace(BASE_DIR=str(app_dir), DATABASE_URL="", BACKUP_DIR=str(dischi / "backup-esterni"))
    monkeypatch.setattr(config, "cfg", test_cfg)
    monkeypatch.setattr(backup_manager, "cfg", test_cfg)
    if hasattr(backup_manager, "BACKUP_DIR"):
        # La versione precedente tiene la cartella in una costante di modulo,
        # calcolata all'import: senza questa riga i test scriverebbero nella
        # cartella backup reale del progetto.
        monkeypatch.setattr(backup_manager, "BACKUP_DIR", str(app_dir / "backups"))
    (app_dir / "data").mkdir()
    (app_dir / "data" / "ermes_knowledge.sqlite3").write_bytes(b"finto database")
    return test_cfg


def _cartella_backup(istanza) -> Path:
    """Dove il modulo mette davvero i backup, secondo la sua stessa API."""
    return Path(backup_manager.get_backup_status()["backup_dir"])


# ============================================================
# Le due impostazioni inerti
# ============================================================


def test_the_configured_backup_directory_is_used(istanza):
    """La ragione d'essere della variabile: mettere i backup su un disco
    diverso da quello dei dati."""
    esito = backup_manager.create_backup(label="prova")

    assert Path(esito["path"]).parent == Path(istanza.BACKUP_DIR), (
        f"backup scritto in {Path(esito['path']).parent} invece di {istanza.BACKUP_DIR}"
    )


def test_the_configured_retention_count_is_respected(istanza, monkeypatch):
    monkeypatch.setattr(config, "cfg", istanza.replace(BACKUP_RETENTION_COUNT=3))
    monkeypatch.setattr(backup_manager, "cfg", istanza.replace(BACKUP_RETENTION_COUNT=3))

    for indice in range(5):
        backup_manager.create_backup(label=f"n{indice}")

    assert len(backup_manager.list_backups()) == 3, "la conservazione configurata non ha effetto"


def test_a_backup_is_listed_and_found_where_it_was_written(istanza):
    """Coerenza fra le tre funzioni: se `create_backup` scrive in un posto e
    `list_backups` guarda in un altro, il backup esiste e il sistema dice di
    non averne."""
    esito = backup_manager.create_backup()

    elencati = {voce["name"] for voce in backup_manager.list_backups()}
    assert esito["name"] in elencati
    assert os.path.exists(esito["path"])


# ============================================================
# Il ripristino non deve scrivere fuori da BASE_DIR
# ============================================================


def _archivio_ostile(cartella: Path, nome_membro: str, contenuto: bytes = b"scritto da fuori") -> str:
    cartella.mkdir(parents=True, exist_ok=True)
    percorso = cartella / "ermes_backup_20990101_000000_ostile.tar.gz"
    payload = cartella / "_payload"
    payload.write_bytes(contenuto)
    with tarfile.open(percorso, "w:gz") as tar:
        tar.add(str(payload), arcname=nome_membro)
    payload.unlink()
    return percorso.name[: -len(".tar.gz")]


def test_a_member_escaping_the_base_directory_is_refused(istanza, tmp_path):
    nome = _archivio_ostile(_cartella_backup(istanza), "../../../evasione.txt")
    fuori = tmp_path / "evasione.txt"

    with pytest.raises(ValueError, match="fuori"):
        backup_manager.restore_backup(nome)

    assert not fuori.exists(), "il ripristino ha scritto fuori dalla cartella dell'applicazione"


def test_an_absolute_member_name_is_refused(istanza, tmp_path):
    """`os.path.join(base, "/assoluto")` scarta `base` del tutto."""
    bersaglio = tmp_path / "assoluto.txt"
    nome = _archivio_ostile(_cartella_backup(istanza), str(bersaglio).replace("\\", "/").lstrip("/"))

    # tarfile normalizza via il separatore iniziale, quindi su POSIX il nome
    # arriva relativo ma con la radice dentro: l'unica proprieta' che conta e'
    # che nulla venga scritto fuori da BASE_DIR.
    with contextlib.suppress(ValueError):
        backup_manager.restore_backup(nome)
    assert not bersaglio.exists()


def test_a_dry_run_does_not_report_members_it_would_refuse(istanza):
    """Il dry run serve a decidere se ripristinare: se elenca membri che il
    ripristino reale rifiuta, informa male proprio nel momento in cui viene
    consultato."""
    nome = _archivio_ostile(_cartella_backup(istanza), "../../../evasione.txt")

    with pytest.raises(ValueError):
        backup_manager.restore_backup(nome, dry_run=True)


def test_a_backup_name_with_separators_is_refused(istanza, tmp_path):
    """Il nome arriva dal percorso della rotta
    (`POST /api/backup/restore/{backup_name}`) e finiva in os.path.join senza
    validazione: su Windows la barra rovesciata e' un separatore, quindi
    portava fuori dalla cartella dei backup."""
    esterno = tmp_path / "altrove"
    esterno.mkdir()
    with tarfile.open(esterno / "estraneo.tar.gz", "w:gz"):
        pass

    for nome in ("..\\..\\altrove\\estraneo", "../../altrove/estraneo", "..%2Faltrove"):
        with pytest.raises((ValueError, FileNotFoundError)):
            backup_manager.restore_backup(nome)


# ============================================================
# La funzionalita' legittima deve continuare a funzionare
# ============================================================


def test_a_real_backup_still_restores(istanza):
    esito = backup_manager.create_backup(label="reale")
    db = Path(istanza.BASE_DIR) / "data" / "ermes_knowledge.sqlite3"
    db.write_bytes(b"contenuto sbagliato")

    ripristino = backup_manager.restore_backup(esito["name"])

    assert ripristino["dry_run"] is False
    assert db.read_bytes() == b"finto database"
    assert any("ermes_knowledge" in voce for voce in ripristino["restored"])


def test_a_dry_run_lists_without_writing(istanza):
    esito = backup_manager.create_backup(label="prova")
    db = Path(istanza.BASE_DIR) / "data" / "ermes_knowledge.sqlite3"
    db.write_bytes(b"contenuto sbagliato")

    ripristino = backup_manager.restore_backup(esito["name"], dry_run=True)

    assert ripristino["dry_run"] is True
    assert ripristino["restored"], "il dry run non ha elencato niente"
    assert db.read_bytes() == b"contenuto sbagliato", "il dry run ha scritto"


def test_the_status_reports_the_directory_actually_used(istanza):
    backup_manager.create_backup()

    stato = backup_manager.get_backup_status()

    assert stato["total_backups"] == 1
    assert Path(stato["backup_dir"]) == Path(istanza.BACKUP_DIR)

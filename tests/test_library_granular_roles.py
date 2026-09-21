"""Unit and integration tests for granular library roles (manager, reviewer, editor, viewer)."""

from pathlib import Path

import pytest

from core.library_store import LibraryAccessError, LibraryStore


def test_granular_roles_assignment_and_validation(tmp_path: Path):
    store = LibraryStore(tmp_path / "test_roles.sqlite3")
    lib = store.create_library("Internal Policies", owner_id="alice")

    # Aggiunta ruoli validi: manager, reviewer, editor, viewer
    store.set_library_member(lib["id"], "bob", "manager")
    store.set_library_member(lib["id"], "carol", "editor")
    store.set_library_member(lib["id"], "dave", "reviewer")
    store.set_library_member(lib["id"], "eve", "viewer")

    members = {m["username"]: m["role"] for m in store.list_library_members(lib["id"])}
    assert members["bob"] == "manager"
    assert members["carol"] == "editor"
    assert members["dave"] == "reviewer"
    assert members["eve"] == "viewer"

    # Ruolo non valido deve sollevare ValueError
    with pytest.raises(ValueError, match="Ruolo collaboratore non valido"):
        store.set_library_member(lib["id"], "frank", "superadmin")


def test_manager_delegated_member_management(tmp_path: Path):
    store = LibraryStore(tmp_path / "test_manager.sqlite3")
    lib = store.create_library("Department Docs", owner_id="alice")

    # Bob viene nominato manager
    store.set_library_member(lib["id"], "bob", "manager")
    # Carol viene nominata editor
    store.set_library_member(lib["id"], "carol", "editor")
    # Dave viene nominato reviewer
    store.set_library_member(lib["id"], "dave", "reviewer")

    actor_alice = {"username": "alice", "role": "member"}
    actor_bob = {"username": "bob", "role": "member"}
    actor_carol = {"username": "carol", "role": "member"}
    actor_dave = {"username": "dave", "role": "member"}

    # Proprietario e manager possono gestire membri
    assert store.can_manage_library_members(lib["id"], actor_alice) is True
    assert store.can_manage_library_members(lib["id"], actor_bob) is True

    # Editor e reviewer NON possono gestire membri
    assert store.can_manage_library_members(lib["id"], actor_carol) is False
    assert store.can_manage_library_members(lib["id"], actor_dave) is False


def test_reviewer_read_only_access_vs_editor_write(tmp_path: Path):
    store = LibraryStore(tmp_path / "test_reviewer.sqlite3")
    lib = store.create_library("Auditing Library", visibility="private", owner_id="alice")

    store.set_library_member(lib["id"], "carol", "editor")
    store.set_library_member(lib["id"], "dave", "reviewer")

    actor_carol = {"username": "carol", "role": "member"}
    actor_dave = {"username": "dave", "role": "member"}

    # Carol (editor) ha sia lettura che scrittura
    lib_carol_read = store.get_library(lib["id"], actor=actor_carol, write=False)
    assert lib_carol_read["access_role"] == "editor"
    lib_carol_write = store.get_library(lib["id"], actor=actor_carol, write=True)
    assert lib_carol_write["access_role"] == "editor"

    # Dave (reviewer) ha accesso in lettura
    lib_dave_read = store.get_library(lib["id"], actor=actor_dave, write=False)
    assert lib_dave_read["access_role"] == "reviewer"

    # Dave (reviewer) NON ha accesso in scrittura (solleva LibraryAccessError)
    with pytest.raises(LibraryAccessError):
        store.get_library(lib["id"], actor=actor_dave, write=True)

"""homestead-law's store is the engine's contract on a SQLite backing.

The record invariants (I-6/I-7/I-9/I-11) are tested in `homestead`'s
`test_invariants_store.py`, against every adapter. This file only checks the
*binding*: that this module's `Sidecar`/`Canonical` use the SQLite adapter,
persist to the law database in the shared root, and expose the contract.
"""
from __future__ import annotations

import json

import pytest

from homestead.keep import paths
from homestead.keep.rungs import Classified, Rung
from homestead.keep.store import SIDECAR, SQLiteAdapter
from homestead_law.store import Canonical, RecordExists, Sidecar, key


def test_the_store_persists_to_the_law_database(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    Sidecar().put("custody", "case_number", "primary",
                  Classified(Rung.L3, "FL-1", derived="a case is on file"))
    # a fresh Sidecar reads it back — it is on disk, in the law db
    assert Sidecar().get("custody", "case_number", "primary").payload == "FL-1"
    assert (paths.home() / "homestead-law.db").exists()


def test_the_store_refuses_to_clobber(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    store.put("custody", "note", "n", Classified(Rung.L2, "first"))
    with pytest.raises(RecordExists):
        store.put("custody", "note", "n", Classified(Rung.L2, "second"))


def test_the_store_fails_closed_to_l5(tmp_path, monkeypatch):
    """The contract's fail-closed rule reaches through the binding: a corrupt row
    written straight to the SQLite adapter reads L5."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    SQLiteAdapter(paths.home() / "homestead-law.db").write(
        SIDECAR, key("custody", "deadline", "x"), json.dumps({"rung": "L9", "payload": "x"})
    )
    assert Sidecar().get("custody", "deadline", "x").rung is Rung.L5


def test_canonical_is_read_only_by_type():
    for forbidden in ("put", "write", "update", "delete", "insert"):
        assert not hasattr(Canonical, forbidden)

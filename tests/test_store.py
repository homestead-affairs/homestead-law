"""The record store on SQLite — I-6, I-7, I-9, and I-11 at the storage boundary.

Bite 1 of homestead-law: the file sidecar's successor, re-seated on a table. The
invariants are `homestead.keep.record`'s, and the checks are the same claims made
against a database — several of which the database holds more tightly than a tree
of files did (I-9 is a primary key, not a file lock).
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

from homestead.keep import paths
from homestead.keep.rungs import Classified, Rung
from homestead_law.store import (
    Canonical,
    InvalidKey,
    RecordExists,
    Replaced,
    Sidecar,
    _connect,
    _default_db,
    key,
)


def _raw_put(table, m, it, ii, rung, payload, derived):
    """Write a row straight to the table, bypassing `put`'s validation — to stand
    in for a corrupted, hand-edited, or older-schema row."""
    with _connect(_default_db(), table) as conn:
        conn.execute(
            f"INSERT OR REPLACE INTO {table} "
            "(matter, item_type, item_id, rung, payload, derived) VALUES (?,?,?,?,?,?)",
            (m, it, ii, rung, payload, derived),
        )


# ── the rung travels with the datum, and survives a restart ──────────────────

def test_the_rung_travels_with_the_datum(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    item = Classified(Rung.L3, "FL-2026-00123", derived="a case number is on file")
    store.put("custody", "case_number", "primary", item)

    back = store.get("custody", "case_number", "primary")
    assert back.rung is Rung.L3
    assert back.payload == item.payload
    assert back.derived == item.derived


def test_a_record_survives_the_process_exiting(tmp_path):
    """Written by one process, read by another — the table persists, and nothing
    is held in memory."""
    writer = textwrap.dedent(
        """
        from homestead_law.store import Sidecar
        from homestead.keep.rungs import Classified, Rung
        Sidecar().put("custody", "note", "n1",
            Classified(Rung.L3, "a name and a place", "a note exists"))
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", writer],
        env={"HOMESTEAD_HOME": str(tmp_path), "PATH": ""},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    import os

    os.environ["HOMESTEAD_HOME"] = str(tmp_path)
    try:
        back = Sidecar().get("custody", "note", "n1")
    finally:
        del os.environ["HOMESTEAD_HOME"]
    assert back.rung is Rung.L3
    assert back.payload == "a name and a place"


# ── I-7 · one key ────────────────────────────────────────────────────────────

def test_i7_the_key_is_validated_and_shared():
    assert key("custody", "deadline", "hearing") == ("custody", "deadline", "hearing")
    for bad in ("", "   ", "..", "a/b", "a\\b", ".", "x\x00y"):
        with pytest.raises(InvalidKey):
            key(bad, "deadline", "id")
        with pytest.raises(InvalidKey):
            key("custody", "deadline", bad)


# ── I-9 · writes never silently overwrite ────────────────────────────────────

def test_i9_a_write_refuses_to_clobber(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    assert store.put("custody", "note", "n", Classified(Rung.L2, "first")) is None
    with pytest.raises(RecordExists):
        store.put("custody", "note", "n", Classified(Rung.L2, "second"))
    assert store.get("custody", "note", "n").payload == "first"


def test_i9_an_overwrite_reports_what_it_replaced(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    store.put("custody", "note", "n", Classified(Rung.L2, "first"))
    replaced = store.put("custody", "note", "n", Classified(Rung.L2, "second"), overwrite=True)
    assert isinstance(replaced, Replaced)
    assert replaced.previous.payload == "first"
    assert store.get("custody", "note", "n").payload == "second"


def test_i9_concurrent_writes_do_not_clobber(tmp_path, monkeypatch):
    """The primary key makes the refusal the database's: of N threads racing one
    key, exactly one INSERT wins and the rest hit the constraint and are refused.
    No lock of ours, no O_EXCL — the table cannot hold two rows at one key."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    import threading

    store = Sidecar()
    n = 8
    barrier = threading.Barrier(n)
    outcomes: list[str] = []
    guard = threading.Lock()

    def racer(i: int) -> None:
        barrier.wait()
        try:
            store.put("custody", "note", "n", Classified(Rung.L2, f"writer-{i}"))
            with guard:
                outcomes.append("won")
        except RecordExists:
            with guard:
                outcomes.append("refused")

    threads = [threading.Thread(target=racer, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert outcomes.count("won") == 1, outcomes
    assert outcomes.count("refused") == n - 1


# ── I-11 at the storage boundary — absence fails closed to L5 ────────────────

def test_a_missing_or_unreadable_rung_reads_l5(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    for bad in ("", "L9", "unknown", "3", "True"):
        _raw_put("sidecar", "custody", "deadline", "x", bad, json.dumps("a name"), "d")
        assert Sidecar().get("custody", "deadline", "x").rung is Rung.L5, bad


def test_a_corrupt_payload_reads_l5(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    _raw_put("sidecar", "custody", "deadline", "x", "L3", "{not json", "d")
    assert Sidecar().get("custody", "deadline", "x").rung is Rung.L5


def test_a_derived_form_lost_in_storage_reads_l5(tmp_path, monkeypatch):
    """A stored L3 whose derived form is gone cannot be rebuilt as a valid
    Classified (L3 is served as a stand-in on at least one surface, so it must
    carry one — BUG-5). The read fails closed to L5 rather than raising."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    _raw_put("sidecar", "custody", "deadline", "x", "L3", json.dumps("a name"), None)
    assert Sidecar().get("custody", "deadline", "x").rung is Rung.L5


# ── I-6 · the canonical handle is read-only by type ──────────────────────────

def test_i6_canonical_has_no_write_methods():
    for forbidden in ("put", "write", "update", "delete", "purge", "remove", "drop", "insert"):
        assert not hasattr(Canonical, forbidden), f"Canonical.{forbidden} exists"


def test_canonical_reads_what_the_operator_placed(tmp_path, monkeypatch):
    """The canonical table is grown by the operator's tools (and, on the fleet
    side, by the Postgres sync); the app reads it. Written by hand into the
    canonical table, read back through the same key and fail-closed hydrate."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    _raw_put("canonical", "custody", "filing", "petition", "L4", json.dumps("a diagnosis"), "a filing exists")
    got = Canonical().get("custody", "filing", "petition")
    assert got.rung is Rung.L4
    assert got.payload == "a diagnosis"
    # and the fail-closed rule holds on the canonical read too
    _raw_put("canonical", "custody", "filing", "petition", "L9", json.dumps("a diagnosis"), "d")
    assert Canonical().get("custody", "filing", "petition").rung is Rung.L5


# ── enumeration and the advisory seam ────────────────────────────────────────

def test_records_enumerates_a_matter_with_refs(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    store.put("custody", "courthouse", "main", Classified(Rung.L1, "Dept 4"))
    store.put("custody", "case_number", "primary",
              Classified(Rung.L3, "FL-1", derived="a case is on file"))
    store.put("bankruptcy", "docket", "d1", Classified(Rung.L1, "public"))

    got = dict(store.records("custody"))
    assert set(got) == {("custody", "courthouse", "main"), ("custody", "case_number", "primary")}
    assert got[("custody", "case_number", "primary")].payload == "FL-1"


def test_records_reads_a_corrupt_row_as_l5(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    Sidecar().put("custody", "case_number", "primary", Classified(Rung.L3, "FL-1", derived="d"))
    _raw_put("sidecar", "custody", "notes", "n1", "L3", "{corrupt", None)
    got = dict(Sidecar().records("custody"))
    assert got[("custody", "notes", "n1")].rung is Rung.L5
    assert got[("custody", "case_number", "primary")].rung is Rung.L3


def test_advise_flags_a_misdeclared_stored_record(tmp_path, monkeypatch):
    """The advisory seam carries over: a note declared L4 that holds an SSN is
    content shaped for L5, and Sidecar.advise says so — read-only, non-blocking."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    store.put("custody", "notes", "n1",
              Classified(Rung.L4, "SSN 123-45-6789 for the school form", derived="a note is on file"))
    store.put("custody", "courthouse", "main", Classified(Rung.L1, "Dept 4"))
    assert any(a.category == "ssn" for a in store.advise("custody", "notes", "n1"))
    assert store.advise("custody", "courthouse", "main") == ()


def test_get_missing_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    with pytest.raises(KeyError):
        Sidecar().get("custody", "note", "absent")



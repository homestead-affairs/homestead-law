"""Tests for the real CLI commands (homestead_law.cli).

These test that the CLI wiring works end to end — commands dispatch, Nestor's
seam is bound, records are stored, entities are proposed and resolved, and
court orders are tracked.  Each test uses a throwaway household root so nothing
touches a real store.
"""
from __future__ import annotations

import os
import tempfile

import pytest

nestor = pytest.importorskip("nestor", reason="nestor-meaning not installed")

from homestead_law.cli import run_cli
from homestead_law import nestor_seam


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Every test gets its own household root and a fresh seam state."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    (tmp_path / "keep").mkdir(parents=True, exist_ok=True)
    nestor_seam._bound = False
    nestor_seam._ledger_path = None
    # Reset the cached store
    import homestead_law.nestor_store as ns
    ns._store = None
    ns._store_path = None
    yield


def test_resolve_no_match(capsys):
    rc = run_cli(["resolve", "party", "Nobody Known"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no match" in out


def test_propose_then_resolve(capsys):
    rc = run_cli(["propose", "party", "Jane Doe", "Jane Doe"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "proposed" in out or "sealed" in out

    rc = run_cli(["resolve", "party", "J. Doe"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Jane Doe" in out


def test_resolve_bad_domain(capsys):
    rc = run_cli(["resolve", "bogus", "test"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "unknown domain" in err


def test_put_stores_record(capsys):
    rc = run_cli(["put", "custody", "courthouse", "Test Court"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "stored" in out
    assert "L1" in out


def test_put_party_proposes_entity(capsys):
    rc = run_cli(["put", "custody", "opposing_party", "Alex Smith"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "proposed to party resolver" in out


def test_put_unknown_matter(capsys):
    rc = run_cli(["put", "bogus", "field", "value"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "unknown matter" in err


def test_put_unknown_field(capsys):
    rc = run_cli(["put", "custody", "bogus_field", "value"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "unknown field" in err


def test_deadline_stores(capsys):
    rc = run_cli(["deadline", "custody", "hearing", "2026-10-01", "Test hearing"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "stored" in out
    assert "2026-10-01" in out


def test_queue_empty(capsys):
    rc = run_cli(["queue"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "nothing due" in out


def test_queue_with_deadline(capsys):
    run_cli(["deadline", "custody", "hearing", "2026-10-01", "Test hearing"])
    rc = run_cli(["queue", "--today", "2026-09-25"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Test hearing" in out or "2026-10-01" in out


def test_orders_propose_and_list(capsys):
    rc = run_cli(["orders", "propose", "test question", "test answer"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "proposed" in out

    rc = run_cli(["orders", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "test question" in out
    assert "test answer" in out


def test_orders_check(capsys):
    run_cli(["orders", "propose", "custody arrangement", "joint legal custody"])
    rc = run_cli(["orders", "check", "custody arrangement"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "joint legal custody" in out


def test_orders_check_no_match(capsys):
    rc = run_cli(["orders", "check", "something never proposed"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "(none)" in out


def test_verify_ledger(capsys):
    rc = run_cli(["verify"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "intact" in out


def test_unknown_command(capsys):
    rc = run_cli(["bogus_command"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "unknown command" in err


def test_empty_argv(capsys):
    rc = run_cli([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "commands" in err.lower() or "resolve" in err

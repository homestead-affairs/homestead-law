"""The entry point's argument handling — `--help` and the headless fallback.

`python -m homestead_law` with no recognized flag used to fall straight through
to `view.run()`, so a box with no tkinter (or no display) got a raw
`ModuleNotFoundError` / `TclError` traceback instead of a legible message. This
file locks in the fix: `--help` prints usage and exits 0 without ever touching
tkinter, and the default path degrades to a one-line message and a non-zero
exit rather than raising, when the window can't be opened.

`--smoke` and `--demo` are exercised elsewhere (`test_view.py`'s docstring,
CI); this file only covers the two paths that changed.
"""
from __future__ import annotations

import sys

from homestead_law import __main__ as entry


def test_help_prints_usage_and_exits_zero_without_tkinter(capsys, monkeypatch):
    # If `--help` imported `homestead_law.app.view` (which imports tkinter
    # inside `run()`), this would blow up on a box with no tkinter — so guard
    # by making a tkinter import explode, and prove `--help` never gets there.
    monkeypatch.setitem(sys.modules, "tkinter", None)  # any import raises ImportError

    rc = entry.main(["--help"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "usage" in out
    assert "--smoke" in out
    assert "--demo" in out
    assert "--help" in out

    # -h is the same door.
    rc = entry.main(["-h"])
    assert rc == 0


def test_missing_tkinter_returns_nonzero_with_guidance(capsys, monkeypatch):
    # Simulate a Python build with no tkinter: importing it raises
    # ModuleNotFoundError(name="tkinter"), exactly what happens on most of the
    # boxes this suite runs on.
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "tkinter" or name.startswith("tkinter."):
            raise ModuleNotFoundError("No module named 'tkinter'", name="tkinter")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    rc = entry.main([])

    assert isinstance(rc, int)
    assert rc != 0
    err = capsys.readouterr().err
    assert "--demo" in err
    assert "--smoke" in err


def test_no_display_returns_nonzero_with_guidance(capsys, monkeypatch):
    # tkinter is importable, but opening a window fails the way it does on a
    # headless server/container: TclError "couldn't connect to display". Stub
    # tkinter itself so this doesn't require tkinter to actually be installed
    # (most boxes this suite runs on don't have it) — only that `__main__`
    # catches whatever class its own `import tkinter; tkinter.TclError` is.
    import types

    fake_tkinter = types.ModuleType("tkinter")

    class FakeTclError(Exception):
        pass

    fake_tkinter.TclError = FakeTclError
    monkeypatch.setitem(sys.modules, "tkinter", fake_tkinter)

    def fake_run() -> int:
        raise FakeTclError('couldn\'t connect to display ""')

    monkeypatch.setattr("homestead_law.app.view.run", fake_run)

    rc = entry.main([])

    assert isinstance(rc, int)
    assert rc != 0
    err = capsys.readouterr().err
    assert "--demo" in err
    assert "--smoke" in err

"""Bite 4, end to end — the store → gate → surface pipeline, headless.

`demo.compose_demo` seeds a synthetic custody matter into the store, lists it and
opens two details entirely through `Window` and `serve()`. This is the plan's
'done when' run as a *pipeline* rather than against hand-built records: a real
matter, loaded from disk, composed through the gate — the L4 payload absent from
the list and present in the detail, and no L5 anywhere.

No display is opened; `view.run` (the tkinter drawing) is a thin consumer of this
same `Window`, and is exercised by `python -m homestead.app --smoke`.
"""
from __future__ import annotations

from homestead_law.app import demo
from homestead_law.store import Sidecar


def test_the_pipeline_composes_the_surfaces(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    out = demo.compose_demo(Sidecar())

    # L1 and L3 payloads render on the list.
    assert "Dept 4" in out
    assert "FL-2026-00123" in out
    # the L4 child_name shows its derived form on the list.
    assert "A minor child is named in this matter" in out

    # the L4 child_name payload appears only in the detail line, never on the list.
    list_section, detail_section = out.split("detail child_name", 1)
    assert "A. Rivera, age 8" not in list_section
    assert "A. Rivera, age 8" in detail_section

    # the sealed ssn renders nowhere — its payload is absent and the detail denies.
    assert "123-45-6789" not in out
    assert "deny" in out


def test_open_matter_lists_everything_but_the_sealed_field(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    demo.seed(store)

    window = demo.open_matter(store)
    assert window.state == "list"

    refs = {row.ref for row in window.rows}
    assert ("custody", "ssn", "primary") not in refs          # L5 dropped, no trace
    assert ("custody", "child_name", "primary") in refs       # L4 shown as derived
    assert ("custody", "courthouse", "primary") in refs       # L1 shown
    assert all("123-45-6789" not in row.text for row in window.rows)


def test_the_queue_demo_orders_gates_and_hides_the_cover(tmp_path, monkeypatch):
    """The queue rendered headless: overdue before far-off, the L4 deadline shown
    as its derived instruction (never its date), and the resting cover revealing
    nothing over a single matter (I-31) even though the queue has items."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    out = demo.compose_queue(Sidecar())

    overdue_line = next(i for i, l in enumerate(out.splitlines()) if "overdue by 5" in l)
    hearing_line = next(i for i, l in enumerate(out.splitlines()) if "due in 36" in l)
    assert overdue_line < hearing_line

    assert "A submission is due" in out    # the L4 deadline's derived form
    assert "2026-08-12" not in out         # never the L4 date on the ambient queue
    assert "Nothing is open" in out        # the resting cover, over one matter (I-31)

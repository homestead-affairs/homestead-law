"""homestead-law's entry point.

**I-21: no auto-render on start.** The resting state is the cover; `view.run`
opens on it and draws the list only when the operator opens a matter.

**I-29: the surface holds no domain logic.** The entry point routes to `view`,
which composes through `Window` over the SQLite store and calculates nothing.

Three ways in, plus `--help`:
  * `--help` / `-h` — print this usage and exit 0. Never opens a window.
  * `--smoke` — start, prove every import survived packaging, exit without a
    display. What CI runs against the built artifact.
  * `--demo` — seed a synthetic custody matter into a throwaway store and print
    the list and a detail, composed through the gate. The pipeline, headless, on
    SQLite.
  * default — open the tkinter view on the cover. On a box with no tkinter or
    no display, this fails legibly: a one-line message pointing at `--demo` and
    `--smoke`, and a non-zero exit — never a raw `ModuleNotFoundError` or
    `TclError` traceback.
"""
from __future__ import annotations

import sys

USAGE = """\
usage: python -m homestead_law [--help] [--smoke | --demo]

  --help, -h   show this message and exit
  --smoke      prove every import survived packaging; exit without a display
  --demo       seed a synthetic custody matter and print it, headless
  (default)    open the tkinter view on the cover — requires tkinter and a
               display; falls back to a guidance message if neither is present
"""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if "--help" in argv or "-h" in argv:
        # Handled before any other branch, and before `view` is imported, so
        # `--help` never touches tkinter or a display.
        print(USAGE, end="")
        return 0

    if "--smoke" in argv:
        # Prove the interpreter and every import survived packaging — this
        # module's surfaces, its store, and the engine it pins — and exit without
        # a display.
        from homestead_law import patterns, registry, store  # noqa: F401
        from homestead_law.app import demo, view, window  # noqa: F401
        from homestead_law.packs import custody  # noqa: F401
        print("homestead-law: smoke ok")
        return 0

    if "--demo" in argv:
        # A throwaway household root, so the demo writes synthetic data nowhere
        # real. Compose the surfaces through the gate and print what a view would
        # draw — the store → serve → surface pipeline, on SQLite, without a display.
        import os
        import tempfile

        from homestead_law.app import demo
        from homestead_law.store import Sidecar

        with tempfile.TemporaryDirectory(prefix="homestead-law-demo-") as tmp:
            os.environ["HOMESTEAD_HOME"] = tmp
            store = Sidecar()
            print(demo.compose_demo(store))
            print()
            print(demo.compose_queue(store))
        return 0

    # Imported inside main so the module stays importable on a headless box.
    from homestead_law.app import view

    try:
        import tkinter
    except ModuleNotFoundError as exc:
        # Covers both "no tkinter package at all" (name == "tkinter") and "the
        # package is present but its C extension isn't built" (name ==
        # "_tkinter", the common cause on minimal/CI Python builds).
        if exc.name not in ("tkinter", "_tkinter"):
            raise
        print(
            "homestead-law: tkinter is not available on this interpreter — "
            "try `--demo` (headless pipeline) or `--smoke` (import check) instead.",
            file=sys.stderr,
        )
        return 1

    try:
        return view.run()
    except tkinter.TclError:
        # "couldn't connect to display" and friends — tkinter imports fine but
        # there is nowhere to open a window (e.g. a headless server/container).
        print(
            "homestead-law: no display available to open the window — "
            "try `--demo` (headless pipeline) or `--smoke` (import check) instead.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

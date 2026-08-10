"""homestead-law's entry point.

**I-21: no auto-render on start.** The resting state is the cover; `view.run`
opens on it and draws the list only when the operator opens a matter.

**I-29: the surface holds no domain logic.** The entry point routes to `view`,
which composes through `Window` over the SQLite store and calculates nothing.

Three ways in:
  * `--smoke` — start, prove every import survived packaging, exit without a
    display. What CI runs against the built artifact.
  * `--demo` — seed a synthetic custody matter into a throwaway store and print
    the list and a detail, composed through the gate. The pipeline, headless, on
    SQLite.
  * default — open the tkinter view on the cover.
"""
from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

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
            print(demo.compose_demo(Sidecar()))
        return 0

    # Imported inside main so the module stays importable on a headless box.
    from homestead_law.app import view

    return view.run()


if __name__ == "__main__":
    sys.exit(main())

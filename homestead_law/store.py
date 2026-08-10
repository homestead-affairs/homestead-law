"""homestead-law's store — `homestead.keep`'s adapter seam on a SQLite backing.

The record layer is the engine's now (`homestead.keep.store`), tested there
against every backing. This module is the thin binding: the `Sidecar` and
`Canonical` it ships write to and read from a **SQLite** database in the shared
`/.homestead` root — the self-contained app's backing, no server. The invariants
(I-6/I-7/I-9/I-11) are the engine's contract; here we only choose the backing and
the database.

Law and the ledger share the root — a household's affairs are one thing — and
each keeps its own database in it. The shared **Postgres** engine on the fleet
side is a different adapter behind the same contract, reached through the gated
sync, never a runtime dependency of the shipped app.
"""
from __future__ import annotations

from homestead.keep import paths
from homestead.keep.store import (
    Canonical as _Canonical,
    Due,
    InvalidKey,
    RecordExists,
    Ref,
    Replaced,
    Sidecar as _Sidecar,
    SQLiteAdapter,
    key,
)

__all__ = [
    "key", "InvalidKey", "RecordExists", "Replaced", "Due", "Ref",
    "Sidecar", "Canonical",
]


def _adapter() -> SQLiteAdapter:
    """This module's database — its own file in the shared `/.homestead` root."""
    return SQLiteAdapter(paths.home() / "homestead-law.db")


class Sidecar(_Sidecar):
    """The app's writable store, on SQLite in the law database."""

    def __init__(self) -> None:
        super().__init__(_adapter())


class Canonical(_Canonical):
    """The read-only canonical handle, on SQLite in the law database."""

    def __init__(self) -> None:
        super().__init__(_adapter())

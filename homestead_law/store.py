"""The record store, on SQLite — the file sidecar's successor (bite 1).

`homestead.keep` gives the model — `Classified`, the rung, the gate — and the
`/.homestead` root every module shares. This is where a legal matter's records
*live*, and on this module it is a table, not a tree of JSON files: deadlines and
matters want joins and indexed lookups, and a row keyed by `(matter, item_type,
item_id)` is what the file layout was approximating.

The record invariants carry over from `homestead.keep.record`, re-seated on the
database — and several get *stronger* for it:

* **I-6 — the canonical record is read-only, enforced by type.** Two handles.
  `Canonical` reads the canonical table and has no `put`/`update`/`delete`; the
  app cannot mutate canonical data even by mistake. `Sidecar` writes its own
  table. The Postgres sync target is the shared canonical on the fleet side; here
  the split is local.
* **I-7 — one key.** `(matter, item_type, item_id)` is the composite **primary
  key**, computed once by `key()` and shared by read and write. BUG-11 was two
  call sites deriving the same key differently; a primary key cannot be derived
  two ways.
* **I-9 — writes never silently overwrite.** A first write is a plain `INSERT`;
  the primary key makes a second one an `IntegrityError`, refused — **race-safe
  by the database**, no lock and no O_EXCL dance. An explicit overwrite reports
  what it replaced.
* **I-11 at the storage boundary — absence fails closed to `L5`.** A row whose
  rung is missing, unreadable, or whose payload will not decode reads `L5` on the
  way out, never `L1`, using the same `rungs._read_rung` the gate uses.

The store is the one place a record's raw payload lives outside the gate — the
chokepoint that will guard the app (when it is extracted onto this store) exempts
exactly the store and the gate, as it does in `homestead`.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from homestead.keep import paths
from homestead.keep.rungs import Classified, Rung, _read_rung

__all__ = ["key", "InvalidKey", "RecordExists", "Replaced", "Sidecar", "Canonical"]

Ref = tuple[str, str, str]

_SIDECAR = "sidecar"
_CANONICAL = "canonical"


class InvalidKey(ValueError):
    """A key component that is not a usable identifier — empty, whitespace-only,
    or carrying a separator or NUL. A key is `(matter, item_type, item_id)`, and
    each component is an identifier, not a path: the separator check is kept from
    the file store so the two stay swappable behind one contract later, and
    because an id with a slash in it is a mistake wherever it lands."""


class RecordExists(Exception):
    """A write refused because the key is occupied (I-9). The store never
    silently overwrites; the caller passes `overwrite=True` to replace, and is
    handed what it displaced."""


@dataclass(frozen=True)
class Replaced:
    """What an explicit overwrite displaced (I-9), so a replacement never loses
    the prior record silently."""

    key: Ref
    previous: Classified


def key(matter: str, item_type: str, item_id: str) -> Ref:
    """Validate and return `(matter, item_type, item_id)` — the one place the key
    is formed (I-7). Read and write both call this, so a record is filed and
    found by the same computation."""
    for name, value in (("matter", matter), ("item_type", item_type), ("item_id", item_id)):
        if not isinstance(value, str) or not value.strip():
            raise InvalidKey(f"{name} must be a non-empty string, not {value!r}")
        if value != value.strip():
            raise InvalidKey(f"{name}={value!r} has surrounding whitespace")
        if "/" in value or "\\" in value or value in (".", "..") or "\x00" in value:
            raise InvalidKey(
                f"{name}={value!r} is not a single identifier — a separator, a "
                "'..', or a NUL is not part of a key"
            )
    return (matter, item_type, item_id)


def _hydrate(row: sqlite3.Row) -> Classified:
    """A `Classified` from a stored row, failing closed to `L5` (I-11).

    The rung is read with `rungs._read_rung` — the same function the gate uses —
    so a `bool`, an integer, `"L9"` or a NULL rung all read as unclassified, and
    unclassified reads `L5`, never `L1`. A payload that will not decode, or a
    readable rung that cannot form a valid `Classified` (an `L3` whose derived
    form is gone), also fails closed to `L5`. Absence at this boundary is served
    as nothing.
    """
    raw_payload = row["payload"]
    try:
        payload = json.loads(raw_payload) if raw_payload is not None else None
    except (ValueError, TypeError):
        return Classified(Rung.L5, None)

    rung = _read_rung(row["rung"])
    if rung is None:
        return Classified(Rung.L5, payload)
    try:
        return Classified(rung, payload, row["derived"])
    except Exception:
        return Classified(Rung.L5, payload)


@contextmanager
def _connect(db_path: Path, table: str) -> Iterator[sqlite3.Connection]:
    """A connection with the table ensured, committed on success and always
    closed. `busy_timeout` makes a racing writer *wait* for the write lock and
    then hit the primary-key conflict (an `IntegrityError` → `RecordExists`),
    rather than failing with 'database is locked' — so I-9's refusal is the
    database's, deterministically."""
    paths.ensure(db_path.parent)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute(
        f"CREATE TABLE IF NOT EXISTS {table} ("
        "  matter    TEXT NOT NULL,"
        "  item_type TEXT NOT NULL,"
        "  item_id   TEXT NOT NULL,"
        "  rung      TEXT NOT NULL,"
        "  payload   TEXT,"
        "  derived   TEXT,"
        "  PRIMARY KEY (matter, item_type, item_id)"
        ")"
    )
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _default_db() -> Path:
    """The household's law database, under the shared `/.homestead` root. Law and
    the ledger share the root — a household's affairs are one thing — and each
    keeps its own database in it."""
    return paths.home() / "homestead-law.db"


class _Reader:
    """The read half both handles share — `get`, `has`, `records`, `advise` — over
    one named table. `Canonical` and `Sidecar` differ only in which table they
    read and whether they can also write."""

    _table: str

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._db = Path(db_path) if db_path is not None else _default_db()

    def get(self, matter: str, item_type: str, item_id: str) -> Classified:
        m, it, ii = key(matter, item_type, item_id)
        with _connect(self._db, self._table) as conn:
            row = conn.execute(
                f"SELECT rung, payload, derived FROM {self._table} "
                "WHERE matter=? AND item_type=? AND item_id=?",
                (m, it, ii),
            ).fetchone()
        if row is None:
            raise KeyError(f"{m}/{it}/{ii}: no such record")
        return _hydrate(row)

    def has(self, matter: str, item_type: str, item_id: str) -> bool:
        m, it, ii = key(matter, item_type, item_id)
        with _connect(self._db, self._table) as conn:
            row = conn.execute(
                f"SELECT 1 FROM {self._table} WHERE matter=? AND item_type=? AND item_id=?",
                (m, it, ii),
            ).fetchone()
        return row is not None

    def records(self, matter: str) -> list[tuple[Ref, Classified]]:
        """Every stored record for a matter, each with its key as a reference — a
        reference, not content (I-15). `matter` is validated as a real identifier
        before it reaches the query."""
        key(matter, "_probe_", "_probe_")
        with _connect(self._db, self._table) as conn:
            rows = conn.execute(
                f"SELECT matter, item_type, item_id, rung, payload, derived "
                f"FROM {self._table} WHERE matter=? ORDER BY item_type, item_id",
                (matter,),
            ).fetchall()
        return [((r["matter"], r["item_type"], r["item_id"]), _hydrate(r)) for r in rows]

    def advise(self, matter: str, item_type: str, item_id: str) -> tuple:
        """Advisory PII check over one stored record — read-only, non-blocking.
        Reuses `homestead.keep.advise`; the store holds the content, so this is
        where the matcher can be handed it without a surface reaching a payload."""
        from homestead.keep.advise import advise as _advise

        record = self.get(matter, item_type, item_id)
        return _advise(record.rung, record.payload)


class Canonical(_Reader):
    """A read-only handle over the canonical record (I-6, I-36).

    Read-only **by type**: no `put`, `update`, `delete`, `purge`, `remove` or
    `drop`. On this module the canonical table is grown by the operator's own
    tools and, on the fleet side, by the Postgres sync; the app reads it and never
    edits or deletes it — auto-purging a live matter is destroying evidence on a
    schedule (I-36).
    """

    _table = _CANONICAL


class Sidecar(_Reader):
    """The app's own record table — the only handle that writes (I-6).

    Keyed the same way as the canonical record and living in the same database. A
    write refuses an occupied key unless overwrite is asked for explicitly, and a
    read fails closed to `L5`.
    """

    _table = _SIDECAR

    def put(
        self,
        matter: str,
        item_type: str,
        item_id: str,
        item: Classified,
        *,
        overwrite: bool = False,
    ) -> Replaced | None:
        """Persist a `Classified`. Refuse an occupied key, or report the
        replacement (I-9). Returns `None` on a first write, a `Replaced` on an
        explicit overwrite.

        Takes a `Classified` and nothing else: an unclassified value has no rung
        to store and must not acquire one here (I-11). A first write is an
        `INSERT`; the primary key makes a racing second write an `IntegrityError`,
        refused — the check and the write are one atomic act, held by the
        database rather than a lock.
        """
        if not isinstance(item, Classified):
            raise TypeError(
                f"put() stores a Classified, not {type(item).__name__} — an "
                "unclassified value has no rung, and the store is not where one "
                "gets invented (I-11)"
            )
        ref = key(matter, item_type, item_id)
        row = (item.rung.value, json.dumps(item.payload), item.derived)

        with _connect(self._db, self._table) as conn:
            if not overwrite:
                try:
                    conn.execute(
                        f"INSERT INTO {self._table} "
                        "(matter, item_type, item_id, rung, payload, derived) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (*ref, *row),
                    )
                except sqlite3.IntegrityError:
                    raise RecordExists(
                        f"{ref[0]}/{ref[1]}/{ref[2]} already exists. A write never "
                        "silently overwrites (I-9, BUG-8): pass overwrite=True to "
                        "replace it, and the prior record is handed back."
                    )
                return None

            existing = conn.execute(
                f"SELECT rung, payload, derived FROM {self._table} "
                "WHERE matter=? AND item_type=? AND item_id=?",
                ref,
            ).fetchone()
            previous = _hydrate(existing) if existing is not None else None
            conn.execute(
                f"INSERT INTO {self._table} "
                "(matter, item_type, item_id, rung, payload, derived) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(matter, item_type, item_id) DO UPDATE SET "
                "rung=excluded.rung, payload=excluded.payload, derived=excluded.derived",
                (*ref, *row),
            )
            return Replaced(key=ref, previous=previous) if previous is not None else None

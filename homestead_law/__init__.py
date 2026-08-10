"""Homestead · Affairs — module one: the legal module (prose name **Law Gazelle**).

The household handling its own deeds and disputes. This module ships
self-contained on embedded **SQLite** and pins **`homestead.keep`** — the
import-pure record, deadline, rung and gate core — by immutable ref. The engine
is shared across the face; the domain (matters, packs, the queue, the app) is
this module's.

The shared **Postgres** engine on the fleet side is a *sync target*, reached
through the egress gate, never a runtime dependency of the shipped app: a clinic
that never heard of Willow installs this and it works.
"""

"""Matter packs — the legal schemas the engine classifies and serves.

A pack is a **closed schema** authored here: every field declares a rung, its
matter type and its jurisdiction, and the pack classifies itself at import
(against `homestead.keep.rungs.classify_schema`) so an unclassified field is a
build failure (I-11), never a runtime surprise. Packs are fixed in v1 — a
household operator files their records in the fields the pack defines and does not
add fields of their own.

Matter packs live *inside* this module (not the org) and belong to the
**registry** — custody is the one built pack; bankruptcy and workers' comp are
later, and adding one touches no navigation, queue or briefing code
(`homestead_law.registry`, I-23).
"""

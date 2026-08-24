"""Text intake — extract structure from raw text, no agent in the loop.

Takes raw text (court notices, call notes, letters) and pulls out dates,
party names, legal citations, case numbers, and court references using
anchored regex.  Pure extraction — never stores, never proposes, never
seals.  The caller decides what to keep.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from homestead_law.patterns import CITATION

__all__ = ["Extracted", "extract"]


@dataclass(frozen=True)
class Extracted:
    """One item pulled from raw text."""

    kind: str
    text: str
    value: str
    start: int
    end: int
    field: str | None = None


# ── date patterns ─────────────────────────────────────────────────────────

_MONTHS: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dec": "12",
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

_DATE_WRITTEN = re.compile(
    rf"\b(?P<month>{_MONTH_RE})\.?\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
_DATE_ISO = re.compile(
    r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b",
)
_DATE_US = re.compile(
    r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\b",
)


# ── party patterns ────────────────────────────────────────────────────────

_VS = re.compile(
    r"\b([A-Z][a-zA-Z'-]+(?:[ \t]+[A-Z][a-zA-Z'-]+){0,3})"
    r"\s+v\.\s+"
    r"([A-Z][a-zA-Z'-]+(?:[ \t]+[A-Z][a-zA-Z'-]+){0,3})\b"
)
_ROLE = re.compile(
    r"(?:Petitioner|Respondent|Plaintiff|Defendant|Applicant|Claimant)"
    r"[:\s]+([A-Z][a-zA-Z'-]+(?:[ \t]+[A-Z][a-zA-Z'-]+){0,3})",
)
_IN_RE = re.compile(
    r"In\s+[Rr]e\s+"
    r"(?:Marriage|Parentage|Guardianship|Adoption)\s+of\s+"
    r"([A-Z][a-zA-Z'-]+(?:[ \t]+(?:[Aa]nd[ \t]+)?[A-Z][a-zA-Z'-]+){0,3})",
)


# ── case number ───────────────────────────────────────────────────────────

_CASE_NO = re.compile(
    r"(?:(?:Case|Docket|File)[ \t]+(?:(?:No\.?|Number|#)[ \t]+)?|No\.[ \t]*)"
    r"([A-Z0-9]\w*(?:-\w+)+)",
    re.IGNORECASE,
)


# ── court name ────────────────────────────────────────────────────────────

_COURT = re.compile(
    r"\b("
    r"(?:(?:Superior|Family|District|Circuit|Municipal|Probate|Juvenile|"
    r"Supreme|Appellate|Federal|County|State)[ \t]+)"
    r"Court"
    r"(?:[ \t]+of[ \t]+[A-Za-z]+(?:[ \t]+[A-Za-z]+){0,3})?"
    r"|"
    r"Court[ \t]+of[ \t]+[A-Z][a-zA-Z]+(?:[ \t]+[A-Za-z]+){0,3}"
    r")\b"
)


# ── extraction ────────────────────────────────────────────────────────────

def _valid_date(year: int, month: int, day: int) -> bool:
    return 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100


def extract(text: str) -> list[Extracted]:
    """Extract structured items from raw text, sorted by position."""
    items: list[Extracted] = []
    seen: set[tuple[int, int, str]] = set()

    def _add(
        kind: str, matched: str, value: str,
        start: int, end: int, field: str | None = None,
    ) -> None:
        key = (start, end, kind)
        if key not in seen:
            seen.add(key)
            items.append(Extracted(kind, matched, value, start, end, field))

    # ISO dates
    for m in _DATE_ISO.finditer(text):
        y, mo, d = int(m["year"]), int(m["month"]), int(m["day"])
        if _valid_date(y, mo, d):
            _add("date", m.group(), f"{y:04d}-{mo:02d}-{d:02d}",
                 m.start(), m.end(), "hearing_date")

    # Written dates (August 15, 2026 / Aug. 15 2026)
    for m in _DATE_WRITTEN.finditer(text):
        mo_num = int(_MONTHS[m["month"].lower()])
        d, y = int(m["day"]), int(m["year"])
        if _valid_date(y, mo_num, d):
            _add("date", m.group(), f"{y:04d}-{mo_num:02d}-{d:02d}",
                 m.start(), m.end(), "hearing_date")

    # US dates (8/15/2026)
    for m in _DATE_US.finditer(text):
        mo, d, y = int(m["month"]), int(m["day"]), int(m["year"])
        if _valid_date(y, mo, d):
            _add("date", m.group(), f"{y:04d}-{mo:02d}-{d:02d}",
                 m.start(), m.end(), "hearing_date")

    # Legal citations (closed-set reporter)
    for m in CITATION.finditer(text):
        _add("citation", m.group(),
             f"{m['volume']} {m['reporter']} {m['page']}",
             m.start(), m.end())

    # Parties — v. pattern (Smith v. Rivera)
    for m in _VS.finditer(text):
        _add("party", m.group(1), m.group(1),
             m.start(1), m.end(1), "opposing_party")
        _add("party", m.group(2), m.group(2),
             m.start(2), m.end(2), "opposing_party")

    # Parties — role labels (Petitioner: Jordan Rivera)
    for m in _ROLE.finditer(text):
        _add("party", m.group(1), m.group(1),
             m.start(1), m.end(1), "opposing_party")

    # Parties — In re Marriage of ...
    for m in _IN_RE.finditer(text):
        _add("party", m.group(1), m.group(1),
             m.start(1), m.end(1), "opposing_party")

    # Case numbers
    for m in _CASE_NO.finditer(text):
        _add("case_number", m.group(), m.group(1),
             m.start(), m.end(), "case_number")

    # Court names
    for m in _COURT.finditer(text):
        _add("court", m.group(1), m.group(1),
             m.start(1), m.end(1), "courthouse")

    items.sort(key=lambda e: e.start)
    return items

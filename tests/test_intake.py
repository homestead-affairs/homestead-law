"""Tests for text intake extraction (homestead_law.intake).

The extraction is pure regex over raw text — no Nestor, no store, no
household root.  These tests run unconditionally.
"""
from __future__ import annotations

from homestead_law.intake import Extracted, extract


# ── dates ─────────────────────────────────────────────────────────────────

def test_iso_date():
    items = extract("Hearing on 2026-09-15 at 9am")
    dates = [i for i in items if i.kind == "date"]
    assert len(dates) == 1
    assert dates[0].value == "2026-09-15"
    assert dates[0].field == "hearing_date"


def test_written_date():
    items = extract("The hearing is set for August 15, 2026")
    dates = [i for i in items if i.kind == "date"]
    assert len(dates) == 1
    assert dates[0].value == "2026-08-15"


def test_written_date_abbreviated():
    items = extract("Filed Sep 3, 2026")
    dates = [i for i in items if i.kind == "date"]
    assert len(dates) == 1
    assert dates[0].value == "2026-09-03"


def test_written_date_no_comma():
    items = extract("Due Jan 10 2027")
    dates = [i for i in items if i.kind == "date"]
    assert len(dates) == 1
    assert dates[0].value == "2027-01-10"


def test_us_date():
    items = extract("Filed on 8/15/2026")
    dates = [i for i in items if i.kind == "date"]
    assert len(dates) == 1
    assert dates[0].value == "2026-08-15"


def test_invalid_date_rejected():
    items = extract("Date: 2026-13-45")
    dates = [i for i in items if i.kind == "date"]
    assert len(dates) == 0


def test_invalid_us_date_rejected():
    items = extract("Ref: 99/99/2026")
    dates = [i for i in items if i.kind == "date"]
    assert len(dates) == 0


# ── citations ─────────────────────────────────────────────────────────────

def test_citation():
    items = extract("See 347 F.3d 1120 for the standard")
    cites = [i for i in items if i.kind == "citation"]
    assert len(cites) == 1
    assert "347" in cites[0].value
    assert "1120" in cites[0].value


def test_citation_does_not_match_address():
    """F-3 regression: an address must never wear the citation pattern."""
    items = extract("Lives at 1420 Maple 87501")
    cites = [i for i in items if i.kind == "citation"]
    assert len(cites) == 0


# ── parties ───────────────────────────────────────────────────────────────

def test_vs_party():
    items = extract("In the matter of Smith v. Rivera")
    parties = [i for i in items if i.kind == "party"]
    names = {p.value for p in parties}
    assert "Smith" in names
    assert "Rivera" in names


def test_vs_multi_word():
    items = extract("Jordan Rivera v. Alex Chen-Williams")
    parties = [i for i in items if i.kind == "party"]
    names = {p.value for p in parties}
    assert "Jordan Rivera" in names
    assert "Alex Chen-Williams" in names


def test_role_party():
    items = extract("Petitioner: Jordan Rivera")
    parties = [i for i in items if i.kind == "party"]
    assert len(parties) == 1
    assert parties[0].value == "Jordan Rivera"


def test_respondent():
    items = extract("Respondent: Alex Chen")
    parties = [i for i in items if i.kind == "party"]
    assert len(parties) == 1
    assert parties[0].value == "Alex Chen"


def test_in_re():
    items = extract("In re Marriage of Smith")
    parties = [i for i in items if i.kind == "party"]
    assert len(parties) == 1
    assert "Smith" in parties[0].value


def test_in_re_and():
    items = extract("In re Marriage of Smith and Rivera")
    parties = [i for i in items if i.kind == "party"]
    assert len(parties) == 1
    assert "Smith" in parties[0].value
    assert "Rivera" in parties[0].value


def test_party_field_default():
    items = extract("Defendant: Jane Doe")
    parties = [i for i in items if i.kind == "party"]
    assert parties[0].field == "opposing_party"


# ── case numbers ──────────────────────────────────────────────────────────

def test_case_number():
    items = extract("Case No. 24-FL-12345 was filed")
    cases = [i for i in items if i.kind == "case_number"]
    assert len(cases) == 1
    assert "24-FL-12345" in cases[0].value


def test_docket_number():
    items = extract("Docket 2024-CV-00789")
    cases = [i for i in items if i.kind == "case_number"]
    assert len(cases) == 1
    assert "2024-CV-00789" in cases[0].value


def test_case_number_field():
    items = extract("Case No. 24-FL-12345")
    cases = [i for i in items if i.kind == "case_number"]
    assert cases[0].field == "case_number"


# ── courts ────────────────────────────────────────────────────────────────

def test_superior_court():
    items = extract("Filed in the Superior Court of California")
    courts = [i for i in items if i.kind == "court"]
    assert len(courts) == 1
    assert "Superior Court" in courts[0].value


def test_family_court():
    items = extract("Family Court, Dept 3")
    courts = [i for i in items if i.kind == "court"]
    assert len(courts) == 1
    assert courts[0].value == "Family Court"


def test_court_of_appeals():
    items = extract("the Court of Appeals ruled")
    courts = [i for i in items if i.kind == "court"]
    assert len(courts) == 1
    assert "Court of Appeals" in courts[0].value


def test_bare_court_not_matched():
    items = extract("We went to court today")
    courts = [i for i in items if i.kind == "court"]
    assert len(courts) == 0


def test_court_field():
    items = extract("Superior Court of California")
    courts = [i for i in items if i.kind == "court"]
    assert courts[0].field == "courthouse"


# ── combined ──────────────────────────────────────────────────────────────

def test_multiple_kinds():
    text = """
    NOTICE OF HEARING
    Case No. 24-FL-12345
    Superior Court of California
    Petitioner: Jordan Rivera
    Hearing Date: September 15, 2026
    """
    items = extract(text)
    kinds = {i.kind for i in items}
    assert "case_number" in kinds
    assert "court" in kinds
    assert "party" in kinds
    assert "date" in kinds


def test_sorted_by_position():
    text = "On 2026-01-01 Smith v. Rivera appeared"
    items = extract(text)
    assert all(items[i].start <= items[i + 1].start for i in range(len(items) - 1))


# ── edge cases ────────────────────────────────────────────────────────────

def test_empty_text():
    assert extract("") == []


def test_no_matches():
    assert extract("Just some regular text with no legal content.") == []


def test_dataclass_frozen():
    items = extract("Hearing on 2026-09-15")
    import pytest
    with pytest.raises(AttributeError):
        items[0].kind = "other"  # type: ignore[misc]

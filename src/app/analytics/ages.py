"""Which ages are safe to decide things with."""

from __future__ import annotations


def sure_age(row: dict) -> int | None:
    """His age, unless it came from a name match alone on Wikidata (``dob_basis == "name"``).

    Such an age is shown with a "?" because it may belong to a namesake, so it never decides who is in an age filter,
    a similar-player search or a "young talent" highlight. Squad-list, club-confirmed and manual ages all count.
    """
    return None if row.get("dob_basis") == "name" else row.get("age")

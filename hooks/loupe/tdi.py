"""Technical Debt Index: unweighted finding counts, trended over turns.

The index is the raw number of findings a turn produced, broken down by
category. Raw counts are the whole point: a weighting formula would need
tuning nobody has data for yet, and an unweighted count trends honestly
from day one. Weighting is deferred until the trend itself shows a need.

One entry is appended per turn that produced findings, at ``Stop``.
Clean turns append nothing, so the history is a record of debt events
rather than a mostly-zero time series.

Entry shape::

    {"ts": "2026-08-02T09:15:00Z", "counts": {"stub": 2, "style": 5}, "total": 7}

``HISTORY_LIMIT`` caps the stored history; the oldest entries are dropped
first, so state cannot grow without bound on a long-lived project.
"""

from collections import Counter
from datetime import datetime, timezone

HISTORY_LIMIT = 500


def score(findings) -> dict:
    """Count ``findings`` by category into a TDI entry body.

    Accepts both ``Finding`` objects and the plain dicts the runtime state
    stores; anything without a readable category is ignored rather than
    counted as an unknown, so a corrupt state entry cannot inflate debt.
    """
    counts = Counter()
    for finding in findings:
        category = getattr(finding, "category", None)
        if category is None and isinstance(finding, dict):
            category = finding.get("category")
        if isinstance(category, str) and category:
            counts[category] += 1
    return {"counts": dict(counts), "total": sum(counts.values())}


def update_tdi(history, findings, now: datetime | None = None) -> list:
    """Return ``history`` with this turn's entry appended.

    A turn with no findings appends nothing and returns the history
    unchanged. ``now`` is injectable so tests do not depend on the clock.
    """
    body = score(findings)
    if body["total"] == 0:
        return _clean(history)
    stamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    entry = {"ts": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"), **body}
    return [*_clean(history), entry][-HISTORY_LIMIT:]


def trend(history) -> dict:
    """Summarize ``history`` for reporting.

    Returns the entry count, the latest total, the sum of all totals, and
    ``direction``: ``"up"``, ``"down"``, or ``"flat"`` comparing the last
    entry against the one before it. An empty or single-entry history is
    ``"flat"`` - there is nothing to compare yet, and guessing a direction
    from one point would be a lie.
    """
    entries = _clean(history)
    if not entries:
        return {"entries": 0, "latest": 0, "lifetime": 0, "direction": "flat"}
    latest = entries[-1]["total"]
    lifetime = sum(entry["total"] for entry in entries)
    if len(entries) < 2:
        direction = "flat"
    else:
        previous = entries[-2]["total"]
        direction = (
            "up" if latest > previous else "down" if latest < previous else "flat"
        )
    return {
        "entries": len(entries),
        "latest": latest,
        "lifetime": lifetime,
        "direction": direction,
    }


def _clean(history) -> list:
    """Drop malformed entries so corrupt state cannot crash reporting or
    poison a trend."""
    return [
        entry
        for entry in history
        if isinstance(entry, dict)
        and isinstance(entry.get("ts"), str)
        and isinstance(entry.get("total"), int)
        and not isinstance(entry.get("total"), bool)
        and isinstance(entry.get("counts"), dict)
    ]

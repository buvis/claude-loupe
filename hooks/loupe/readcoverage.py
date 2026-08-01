"""Read line-range bookkeeping for the out-of-range edit guard.

Tracks which line ranges of each file the agent has read this session and
answers whether an edit's target lines fall inside them. Ranges are stored
as inclusive ``[start, end]`` pairs, normalized so the stored list is
always sorted and non-overlapping - two reads of lines 1-100 and 101-200
merge into one 1-200 range, which is what makes a subsequent whole-file
edit legal.

A whole-file read (no offset and no limit) is recorded as ``[1, END]``
with ``END = FULL_FILE``, a sentinel large enough to cover any real
source file. Using a sentinel rather than the true line count keeps this
module pure: it never touches the filesystem.

All functions are pure; callers own state I/O.
"""

FULL_FILE = 1_000_000_000


def merge_range(ranges, start: int, end: int) -> list:
    """Return ``ranges`` with ``[start, end]`` merged in, sorted and coalesced.

    Adjacent ranges coalesce (1-100 and 101-200 become 1-200) because a
    gap of zero lines is not a gap. An invalid range (``end < start``) is
    ignored rather than stored.
    """
    if end < start:
        return _normalize(ranges)
    return _normalize([*ranges, [start, end]])


def is_covered(ranges, start: int, end: int) -> bool:
    """True when every line in ``[start, end]`` sits inside one stored range.

    Requires a single covering range: coalescing in ``merge_range`` means
    genuinely contiguous coverage is always stored as one range, so a
    target spanning two stored ranges really does have a hole between them.
    """
    if end < start:
        return True
    return any(r[0] <= start and end <= r[1] for r in _normalize(ranges))


def read_range(offset, limit) -> tuple[int, int]:
    """Map a Read tool's ``offset``/``limit`` to an inclusive line range.

    Both absent means a whole-file read. A bare ``offset`` reads to the
    end of the file. A non-integer or non-positive value is treated as
    absent, so a malformed payload degrades to the widest safe reading
    rather than to a bogus narrow range that would cause false blocks.
    """
    start = offset if isinstance(offset, int) and offset > 0 else 1
    if isinstance(limit, int) and limit > 0:
        return start, start + limit - 1
    return start, FULL_FILE


def _normalize(ranges) -> list:
    """Sorted, coalesced, well-formed ranges; junk entries are dropped."""
    clean = [
        [r[0], r[1]]
        for r in ranges
        if isinstance(r, (list, tuple))
        and len(r) == 2
        and isinstance(r[0], int)
        and isinstance(r[1], int)
        and not isinstance(r[0], bool)
        and not isinstance(r[1], bool)
        and r[0] <= r[1]
    ]
    if not clean:
        return []
    clean.sort()
    merged = [clean[0]]
    for start, end in clean[1:]:
        last = merged[-1]
        if start <= last[1] + 1:
            last[1] = max(last[1], end)
        else:
            merged.append([start, end])
    return merged

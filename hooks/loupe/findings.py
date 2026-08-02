"""Finding record and the blocking vs advisory classification.

Categories are closed: ``stub``, ``security``, ``correctness``, ``style``.
Stub and security findings are blocking - exit 2 in the hook layer, which
stops a pre-write hook outright and returns must-fix feedback from a
post-write one; correctness and style render as advisory. Keeping the split
here, next to the model, means every analysis module classifies identically.

A rule earns ``stub`` only when the pattern has no legitimate use. An empty
``except``/``catch`` does not qualify: the 2026-08-02 dogfood found 30 of them
in shipped first-party code, every one deliberate, so those rules live under
``style``.
"""

from dataclasses import dataclass

CATEGORIES = frozenset({"stub", "security", "correctness", "style"})
BLOCKING_CATEGORIES = frozenset({"stub", "security"})


@dataclass(frozen=True)
class Finding:
    """One analysis finding tied to a location in a file."""

    category: str
    severity: str
    message: str
    path: str
    line: int

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(
                f"unknown finding category {self.category!r}; "
                f"expected one of {sorted(CATEGORIES)}"
            )


def classify(findings) -> tuple[list[Finding], list[Finding]]:
    """Split findings into ``(blocking, advisory)``, preserving order.

    Blocking findings (stubs, security violations) abort the edit;
    everything else is advisory.
    """
    blocking = [f for f in findings if f.category in BLOCKING_CATEGORIES]
    advisory = [f for f in findings if f.category not in BLOCKING_CATEGORIES]
    return blocking, advisory

"""Credential patterns for the pre-write secrets scan.

``scan_for_secrets`` matches content against a small set of credential
shapes and returns the matched category names. The hook layer aborts the
write (exit 2) on any match, so the pattern set tunes for precision over
recall: a false abort on every write is worse than a rare miss. Obvious
placeholders (``example``, ``changeme``, ``xxx``, ``<...>``, ``$``
interpolation, ``{`` templating) never match, and generic assignments
only match when the value is long or high-entropy.
"""

import math
import re
from collections import Counter

# Substrings that mark a value as a placeholder, not a real credential.
# Checked case-insensitively against the matched text.
PLACEHOLDER_MARKERS = (
    "example",
    "changeme",
    "change-me",
    "change_me",
    "placeholder",
    "dummy",
    "sample",
    "your-",
    "your_",
    "xxx",
    "redacted",
    "test",
    "<",
    "$",
    "{",
    "%s",
)

# Passwords that are themselves placeholder words in connection strings.
_PASSWORD_STOPWORDS = frozenset(
    {"pass", "password", "passwd", "pwd", "pw", "secret", "hunter2"}
)

# Hosts that mark a connection string as documentation or local dev.
_DOC_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "host", "hostname"})
_DOC_HOST_SUFFIXES = ("example.com", "example.org", "example.net", "example.io")

# Generic-assignment value gates: match when the quoted literal is long,
# or when it is at least the minimum length and looks random.
_LONG_VALUE_LENGTH = 20
_MIN_VALUE_LENGTH = 12
_ENTROPY_THRESHOLD_BITS = 3.5

_AWS_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")

_GITHUB_RE = re.compile(
    r"\b(?:ghp_[A-Za-z0-9]{36,}|gho_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})"
)

_SLACK_RE = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")

# Header plus up to 400 chars of body; the body must contain a base64-ish
# run to count as a real key, so a bare header in prose stays silent.
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY(?: BLOCK)?-----(?P<body>[\s\S]{0,400})"
)
# Standard base64 without `=`, `-`, `_`: ASCII divider lines (40 dashes,
# RST `====` underlines) must not read as key material.
_KEY_BODY_RE = re.compile(r"[A-Za-z0-9+/]{40}")

_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")

_CONNECTION_RE = re.compile(
    r"\b[A-Za-z][A-Za-z0-9+.-]{1,30}://"
    r"(?P<user>[^/\s:@'\"`]{1,64}):(?P<password>[^/\s@'\"`]{1,256})@(?P<host>[\w.-]+)"
)

# Identifier ending in a credential word, then an assignment-like separator
# (`=` but not `==`, optionally after a type annotation; or `:`, `=>`,
# `:=`), then a quoted literal of 12+ chars.
_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    [\w.$-]* (?: api[_-]?key | apikey | secret | token | passwd | password | pwd )
    ["']?
    (?:
        \s* (?: : \s* [A-Za-z_][\w.\[\], |]* )? \s* (?<![=!<>:])=(?!=)
      | \s* (?: : | => | := )
    )
    \s* ["'] (?P<value> [^"'\n]{12,} ) ["']
    """
)

# Unquoted variant for .env-style files (API_KEY=9f3K...). Restricted to a
# token-ish charset; the value must also contain a digit and not be all
# digits, so function references and numeric ids stay silent.
_ENV_ASSIGNMENT_RE = re.compile(
    r"""(?ix)
    [\w.$-]* (?: api[_-]?key | apikey | secret | token | passwd | password | pwd )
    \s* [:=] \s*
    (?P<value> [A-Za-z0-9_+/=.-]{12,} )
    """
)


def scan_for_secrets(content: str) -> list[str]:
    """Matched credential categories in ``content``, first-hit order, deduped.

    An empty list means the content is clean. Categories:
    ``aws-access-key``, ``github-token``, ``slack-token``, ``private-key``,
    ``jwt``, ``connection-string``, ``credential-assignment``.
    """
    matched: list[str] = []

    def hit(category: str) -> None:
        if category not in matched:
            matched.append(category)

    for pattern, category in (
        (_AWS_RE, "aws-access-key"),
        (_GITHUB_RE, "github-token"),
        (_SLACK_RE, "slack-token"),
        (_JWT_RE, "jwt"),
    ):
        for match in pattern.finditer(content):
            if not _is_placeholder(match.group(0)):
                hit(category)
                break

    for match in _PRIVATE_KEY_RE.finditer(content):
        if _KEY_BODY_RE.search(match.group("body")):
            hit("private-key")
            break

    for match in _CONNECTION_RE.finditer(content):
        if _is_real_connection_password(match.group("password"), match.group("host")):
            hit("connection-string")
            break

    for match in _ASSIGNMENT_RE.finditer(content):
        if _is_secret_value(match.group("value")):
            hit("credential-assignment")
            break
    if "credential-assignment" not in matched:
        for match in _ENV_ASSIGNMENT_RE.finditer(content):
            if _is_env_secret_value(match.group("value")):
                hit("credential-assignment")
                break

    return matched


def _is_placeholder(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in PLACEHOLDER_MARKERS)


def _is_real_connection_password(password: str, host: str) -> bool:
    if _is_placeholder(password):
        return False
    if password.lower() in _PASSWORD_STOPWORDS:
        return False
    host_lowered = host.lower()
    if host_lowered in _DOC_HOSTS:
        return False
    return not any(
        host_lowered == suffix or host_lowered.endswith("." + suffix)
        for suffix in _DOC_HOST_SUFFIXES
    )


def _is_secret_value(value: str) -> bool:
    """Long or high-entropy quoted literals count as secrets; the rest pass.

    Values with whitespace read as prose, not credentials, and stay silent.
    """
    if _is_placeholder(value) or any(ch.isspace() for ch in value):
        return False
    if len(value) >= _LONG_VALUE_LENGTH:
        return True
    return (
        len(value) >= _MIN_VALUE_LENGTH
        and _entropy_bits_per_char(value) >= _ENTROPY_THRESHOLD_BITS
    )


def _is_env_secret_value(value: str) -> bool:
    """Unquoted values additionally need a digit and must not be all digits.

    Code references (``token=make_token``) carry no digits and numeric ids
    (``token=12345678901234``) carry only digits; real credentials mix both.
    """
    if not any(ch.isdigit() for ch in value) or value.isdigit():
        return False
    return _is_secret_value(value)


def _entropy_bits_per_char(value: str) -> float:
    """Shannon entropy of ``value`` in bits per character."""
    total = len(value)
    if total == 0:
        return 0.0
    return -sum(
        (count / total) * math.log2(count / total)
        for count in Counter(value).values()
    )

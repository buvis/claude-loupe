"""ast-grep rule-pack dispatch for one edited file.

Runs the packaged rule set (``rules/ast-grep`` at the repo root) against
a file and maps matches to findings. The category rides in the rule id
prefix - every pack rule is named ``<category>-<language>-<slug>`` - so
the pack and this parser share one convention and no metadata plumbing.

Failure policy per the PRD error case: an ast-grep crash, timeout, or
unparseable JSON yields a single advisory warning finding, never an
exception. An absent binary skips silently and records a once-per-project
nudge (state is loaded and persisted here; ``record_nudge`` is idempotent,
and concurrent hook writes stay last-wins as documented in state.py).
"""

import json
import subprocess
from pathlib import Path

from .findings import CATEGORIES, Finding
from .project import project_hash
from .state import load_state
from .tools import record_nudge, resolve_tool

ASTGREP_TIMEOUT_SECONDS = 10

# Languages the shipped rule pack covers; anything else skips before any
# subprocess spawn. `.ts` files map to "javascript" in languages.py and
# are scanned by the pack's typescript twin rules.
RULE_LANGUAGES = frozenset({"python", "javascript", "rust"})

# hooks/loupe/astgrep.py -> repo root -> rules/ast-grep
DEFAULT_RULES_DIR = Path(__file__).resolve().parents[2] / "rules" / "ast-grep"

# Line 0 marks a file-level advisory (no specific source line).
FILE_LEVEL_LINE = 0


def run_astgrep(path, language: str, rules_dir=None) -> list[Finding]:
    """Findings from the loupe rule pack for ``path``.

    ``rules_dir`` defaults to the packaged pack; tests point it at their
    own. Returns ``[]`` for languages outside the pack and for an absent
    ast-grep binary (after nudging).
    """
    if language not in RULE_LANGUAGES:
        return []
    binary = resolve_tool("ast-grep")
    if binary is None:
        project = project_hash(Path(path).parent)
        record_nudge(load_state(project), project, "ast-grep")
        return []
    config = Path(rules_dir) if rules_dir is not None else DEFAULT_RULES_DIR
    try:
        result = subprocess.run(
            [
                binary,
                "scan",
                "--config",
                str(config / "sgconfig.yml"),
                "--json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=ASTGREP_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return [_advisory(path, "ast-grep did not complete within the timeout")]
    return _parse(result.stdout, str(path), result.returncode)


def _parse(output: str, path: str, returncode: int) -> list[Finding]:
    """Map ast-grep ``--json`` matches to findings.

    A successful scan always prints a JSON array (``[]`` when clean), so
    unparseable output means the run itself broke and reports as one
    advisory warning.
    """
    try:
        data = json.loads(output)
    except ValueError:
        return [
            _advisory(
                path, f"ast-grep produced no parseable output (exit {returncode})"
            )
        ]
    if not isinstance(data, list):
        return [_advisory(path, "ast-grep emitted unexpected JSON shape")]
    findings = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("ruleId") or "")
        category = rule_id.split("-", 1)[0]
        if category not in CATEGORIES:
            category = "style"
        message = str(item.get("message") or "").strip() or "rule match"
        findings.append(
            Finding(
                category,
                str(item.get("severity") or "warning"),
                f"{rule_id}: {message}" if rule_id else message,
                path,
                _to_one_based(item.get("range", {}).get("start", {}).get("line")),
            )
        )
    return findings


def _to_one_based(line) -> int:
    """ast-grep JSON lines are 0-based (verified against 0.44)."""
    try:
        return int(line) + 1
    except (TypeError, ValueError):
        return 1


def _advisory(path, message: str) -> Finding:
    """File-level advisory warning; keeps failures visible but non-blocking."""
    return Finding("style", "warning", message, str(path), FILE_LEVEL_LINE)

"""Fast per-edit linter dispatch, one language-appropriate tool per file.

Only linters that answer well inside the ~1s per-edit budget run here.
Compile and type-check class linters (clippy, svelte-check) cannot meet
that budget, so they are named in ``SLOW_LINTERS`` for the Phase 2 Stop
queue and never dispatched from this module.

An absent tool skips silently and records a nudge once per project; a
timed-out or crashed linter returns no findings, never raises. Linter
findings are always advisory: categories stay within ``correctness`` and
``style`` so they can never block an edit.
"""

import json
import re
import subprocess
from pathlib import Path

from .findings import Finding
from .project import project_hash
from .tools import record_nudge, resolve_tool

LINTER_TIMEOUT_SECONDS = 10

# Language -> candidate tools, first resolvable wins; the first name is
# also the one nudged when none resolve (Biome is the JS default per PRD).
FAST_LINTERS = {
    "python": ("ruff",),
    "javascript": ("biome", "eslint"),
    "css": ("stylelint",),
    "sql": ("sqlfluff",),
    "ruby": ("rubocop",),
    "shell": ("shellcheck",),
}

# Stop-queue linters, consumed by Phase 2's agent_end hook; kept here so
# the linter inventory lives in one module.
SLOW_LINTERS = {"rust": "clippy", "svelte": "svelte-check"}


def run_linter(path, language: str, config: dict, state: dict):
    """Run the fast linter for ``language`` on ``path``.

    Returns ``(findings, state)``; the state comes back updated when an
    absent tool records its once-per-project nudge. Languages without a
    fast linter (including the ``SLOW_LINTERS`` ones) return no findings
    and leave state untouched. ``config`` is accepted for the hook-layer
    call shape; no v1 config key alters linting.
    """
    candidates = FAST_LINTERS.get(language)
    if not candidates:
        return [], state
    binary = None
    for name in candidates:
        binary = resolve_tool(name)
        if binary:
            break
    if binary is None:
        state, _ = record_nudge(
            state, project_hash(Path(path).parent), candidates[0]
        )
        return [], state
    output = _run(binary, name, str(path))
    if output is None:
        return [], state
    try:
        findings = _PARSERS[name](output, str(path))
    except (ValueError, KeyError, TypeError, AttributeError):
        return [], state
    return findings, state


def _run(binary: str, name: str, path: str):
    """Tool stdout, or ``None`` on timeout/spawn failure.

    The exit code is deliberately ignored: linters exit nonzero when they
    find violations, and the violations are exactly what gets parsed.
    """
    try:
        result = subprocess.run(
            _COMMANDS[name](binary, path),
            capture_output=True,
            text=True,
            timeout=LINTER_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout


_COMMANDS = {
    "ruff": lambda binary, path: [binary, "check", "--output-format=json", path],
    "biome": lambda binary, path: [binary, "lint", "--reporter=github", path],
    "eslint": lambda binary, path: [binary, "--format", "json", path],
    "stylelint": lambda binary, path: [binary, "--formatter", "json", path],
    "sqlfluff": lambda binary, path: [binary, "lint", "--format", "json", path],
    "rubocop": lambda binary, path: [binary, "--format", "json", path],
    "shellcheck": lambda binary, path: [binary, "--format=json", path],
}


def _parse_ruff(output: str, path: str) -> list[Finding]:
    findings = []
    for item in _json_list(output):
        code = str(item.get("code") or "")
        category = (
            "correctness"
            if code.startswith("F") or code.startswith("E9")
            else "style"
        )
        findings.append(
            Finding(
                category,
                "warning",
                _label(code, item.get("message")),
                path,
                _line(item.get("location", {}).get("row")),
            )
        )
    return findings


# GitHub workflow-command lines (biome --reporter=github), parsed
# order-agnostically because parameter order is not contractual.
_GITHUB_LINE_RE = re.compile(
    r"^::(?P<severity>error|warning|notice)\s+(?P<params>.*?)::(?P<message>.*)$"
)


def _parse_biome(output: str, path: str) -> list[Finding]:
    findings = []
    for line in output.splitlines():
        match = _GITHUB_LINE_RE.match(line.strip())
        if not match:
            continue
        params = dict(
            part.split("=", 1)
            for part in match.group("params").split(",")
            if "=" in part
        )
        title = params.get("title", "")
        groups = title.split("/")
        category = (
            "correctness"
            if "suspicious" in groups or "correctness" in groups
            else "style"
        )
        findings.append(
            Finding(
                category,
                match.group("severity"),
                _label(title, match.group("message")),
                path,
                _line(params.get("line")),
            )
        )
    return findings


def _parse_eslint(output: str, path: str) -> list[Finding]:
    findings = []
    for file_entry in _json_list(output):
        for msg in file_entry.get("messages", []):
            error = msg.get("severity") == 2
            findings.append(
                Finding(
                    "correctness" if error else "style",
                    "error" if error else "warning",
                    _label(msg.get("ruleId"), msg.get("message")),
                    path,
                    _line(msg.get("line")),
                )
            )
    return findings


def _parse_stylelint(output: str, path: str) -> list[Finding]:
    findings = []
    for file_entry in _json_list(output):
        for warning in file_entry.get("warnings", []):
            findings.append(
                Finding(
                    "style",
                    str(warning.get("severity") or "warning"),
                    _label(warning.get("rule"), warning.get("text")),
                    path,
                    _line(warning.get("line")),
                )
            )
    return findings


def _parse_sqlfluff(output: str, path: str) -> list[Finding]:
    findings = []
    for file_entry in _json_list(output):
        for violation in file_entry.get("violations", []):
            findings.append(
                Finding(
                    "style",
                    "warning",
                    _label(violation.get("code"), violation.get("description")),
                    path,
                    _line(
                        violation.get("start_line_no", violation.get("line_no"))
                    ),
                )
            )
    return findings


def _parse_rubocop(output: str, path: str) -> list[Finding]:
    try:
        data = json.loads(output)
    except ValueError:
        return []
    if not isinstance(data, dict):
        return []
    findings = []
    for file_entry in data.get("files", []):
        for offense in file_entry.get("offenses", []):
            severity = str(offense.get("severity") or "convention")
            findings.append(
                Finding(
                    "correctness" if severity in ("error", "fatal") else "style",
                    severity,
                    _label(offense.get("cop_name"), offense.get("message")),
                    path,
                    _line(offense.get("location", {}).get("line")),
                )
            )
    return findings


def _parse_shellcheck(output: str, path: str) -> list[Finding]:
    findings = []
    for item in _json_list(output):
        level = str(item.get("level") or "style")
        findings.append(
            Finding(
                "correctness" if level == "error" else "style",
                level,
                _label(f"SC{item.get('code', '')}", item.get("message")),
                path,
                _line(item.get("line")),
            )
        )
    return findings


_PARSERS = {
    "ruff": _parse_ruff,
    "biome": _parse_biome,
    "eslint": _parse_eslint,
    "stylelint": _parse_stylelint,
    "sqlfluff": _parse_sqlfluff,
    "rubocop": _parse_rubocop,
    "shellcheck": _parse_shellcheck,
}


def _json_list(output: str) -> list:
    try:
        data = json.loads(output)
    except ValueError:
        return []
    return data if isinstance(data, list) else []


def _line(value) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 1
    return number if number > 0 else 1


def _label(rule, message) -> str:
    rule_text = str(rule or "").strip()
    message_text = str(message or "").strip()
    if rule_text and message_text:
        return f"{rule_text}: {message_text}"
    return message_text or rule_text or "finding"

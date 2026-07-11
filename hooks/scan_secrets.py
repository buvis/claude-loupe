#!/usr/bin/env python3
"""PreToolUse secrets guard for Write|Edit|MultiEdit: block credential leaks.

Extracts the new content a write/edit is about to land and scans it
with the engine's credential patterns. Any match exits 2, which aborts
the tool call; stderr names the file and the matched categories.
Parsing is defensive (unknown or missing fields exit 0) and the whole
hook fails open (exit 0) on internal errors.
"""

import os
import sys

import gate

_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit"})


def main() -> int:
    try:
        payload = gate.read_hook_json()
        if payload is None:
            return 0
        if payload.get("tool_name") not in _WRITE_TOOLS:
            return 0
        tool_input = payload.get("tool_input")
        if not isinstance(tool_input, dict):
            return 0
        content = _new_content(payload["tool_name"], tool_input)
        if not content:
            return 0
        cwd = str(payload.get("cwd") or "") or os.getcwd()
        if not gate.loupe_enabled(cwd):
            return 0
        return _scan(content, str(tool_input.get("file_path") or "unknown file"))
    except Exception:  # fail open: never break the user's session
        return 0


def _new_content(tool_name: str, tool_input: dict) -> str:
    """The content the tool is about to write; ``""`` when unparseable."""
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else ""
    if tool_name == "Edit":
        new = tool_input.get("new_string")
        return new if isinstance(new, str) else ""
    edits = tool_input.get("edits")
    if not isinstance(edits, list):
        return ""
    parts = [
        edit.get("new_string")
        for edit in edits
        if isinstance(edit, dict) and isinstance(edit.get("new_string"), str)
    ]
    return "\n".join(parts)


def _scan(content: str, target: str) -> int:
    from loupe.secrets import scan_for_secrets

    categories = scan_for_secrets(content)
    if not categories:
        return 0
    print(
        f"loupe: secrets detected in {target}: {', '.join(categories)}. "
        "Write blocked - remove the credential (use an env var or a "
        "secret manager) and retry.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())

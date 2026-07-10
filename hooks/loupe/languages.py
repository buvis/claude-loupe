"""Language detection by file extension.

Families that share linters and rules collapse into one name: JS, JSX,
TS, and TSX are all ``"javascript"``; CSS and SCSS are ``"css"``; the
shell dialects are ``"shell"``. Anything unmapped is ``"unknown"``, which
downstream analysis treats as "skip silently".
"""

from pathlib import Path

UNKNOWN = "unknown"

EXTENSION_LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".rs": "rust",
    ".svelte": "svelte",
    ".css": "css",
    ".scss": "css",
    ".sql": "sql",
    ".rb": "ruby",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".md": "markdown",
    ".markdown": "markdown",
}


def detect_language(path: str | Path) -> str:
    """Language name for a file path; ``"unknown"`` when unmapped."""
    return EXTENSION_LANGUAGES.get(Path(path).suffix.lower(), UNKNOWN)

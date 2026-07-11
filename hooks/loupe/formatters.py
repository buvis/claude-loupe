"""Safe autofix and config-gated formatter dispatch (Stop-queue work).

``apply_autofix`` runs the safe-only fixer for a language (ruff --fix,
biome check --write / eslint --fix, stylelint --fix, sqlfluff fix,
rubocop -a). ``apply_formatters`` runs the project's formatter with
nearest-config-wins resolution: walk up from the file to the project
root, first directory with a recognized formatter config decides; with
no config anywhere, JS-TS falls back to Biome and Python to Ruff per the
PRD, and every other language does nothing.

Both return one result record ``{"path", "step", "tool", "status"}``
with status ``changed`` / ``unchanged`` (content compare), ``skipped``
(no tool or no config), or ``failed`` (spawn error or timeout). Exit
codes are not trusted: fixers exit nonzero whenever unfixable findings
remain, which is not a dispatch failure. Requires Python 3.11+
(tomllib), same floor the engine's ``X | Y`` annotations already set.
"""

import json
import subprocess
import tomllib
from pathlib import Path

from .languages import detect_language
from .project import project_root
from .tools import resolve_tool

FORMAT_TIMEOUT_SECONDS = 30

# Language -> candidate (tool, args-before-path) fixers; first
# resolvable tool runs (Biome preferred over eslint, mirroring linters).
AUTOFIXERS = {
    "python": (("ruff", ("check", "--fix")),),
    "javascript": (("biome", ("check", "--write")), ("eslint", ("--fix",))),
    "css": (("stylelint", ("--fix",)),),
    "sql": (("sqlfluff", ("fix",)),),
    "ruby": (("rubocop", ("-a",)),),
}

_FORMATTER_COMMANDS = {
    "prettier": ("--write",),
    "biome": ("format", "--write"),
    "ruff": ("format",),
    "black": (),
    "rustfmt": (),
}

_PRETTIER_FILES = (
    ".prettierrc",
    ".prettierrc.json",
    ".prettierrc.yml",
    ".prettierrc.yaml",
    ".prettierrc.json5",
    ".prettierrc.js",
    ".prettierrc.cjs",
    ".prettierrc.mjs",
    ".prettierrc.toml",
    "prettier.config.js",
    "prettier.config.cjs",
    "prettier.config.mjs",
)

_BIOME_FILES = ("biome.json", "biome.jsonc")

_RUSTFMT_FILES = ("rustfmt.toml", ".rustfmt.toml")

# PRD defaults for projects with no formatter config at all.
_DEFAULT_FORMATTERS = {"python": "ruff", "javascript": "biome"}


def apply_autofix(path, language: str, config: dict) -> dict:
    """Run the safe autofixer for ``language`` on ``path``.

    ``config`` is accepted for the hook-layer call shape; no v1 config
    key alters autofixing.
    """
    for tool, args in AUTOFIXERS.get(language, ()):
        binary = resolve_tool(tool)
        if binary:
            return _run_step(path, "autofix", tool, binary, args)
    return _result(path, "autofix", None, "skipped")


def apply_formatters(path, config: dict) -> dict:
    """Format ``path`` with the nearest-configured project formatter.

    ``config`` is accepted for the hook-layer call shape; no v1 config
    key alters formatting.
    """
    language = detect_language(path)
    tool = _resolve_formatter(Path(path), language)
    if tool is None:
        return _result(path, "format", None, "skipped")
    binary = resolve_tool(tool)
    if binary is None:
        return _result(path, "format", tool, "skipped")
    return _run_step(path, "format", tool, binary, _FORMATTER_COMMANDS[tool])


def format_summary(results) -> str:
    """One line per file summarizing its fix/format steps."""
    by_path: dict[str, list] = {}
    for result in results:
        by_path.setdefault(result["path"], []).append(result)
    lines = []
    for path, entries in by_path.items():
        parts = [
            f"{entry['step']} {entry['tool']} ({entry['status']})"
            for entry in entries
            if entry["status"] != "skipped"
        ]
        lines.append(f"{path}: {', '.join(parts) if parts else 'nothing to do'}")
    return "\n".join(lines)


def _run_step(path, step: str, tool: str, binary: str, args) -> dict:
    target = Path(path)
    try:
        before = target.read_bytes()
    except OSError:
        return _result(path, step, tool, "failed")
    try:
        subprocess.run(
            [binary, *args, str(path)],
            capture_output=True,
            timeout=FORMAT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _result(path, step, tool, "failed")
    try:
        after = target.read_bytes()
    except OSError:
        return _result(path, step, tool, "failed")
    return _result(path, step, tool, "changed" if after != before else "unchanged")


def _result(path, step: str, tool, status: str) -> dict:
    return {"path": str(path), "step": step, "tool": tool, "status": status}


def _resolve_formatter(path: Path, language: str):
    """Formatter name for ``path``, nearest config first, else PRD default."""
    finder = _CONFIG_FINDERS.get(language)
    if finder is None:
        return None
    for directory in _config_dirs(path):
        tool = finder(directory)
        if tool:
            return tool
    return _DEFAULT_FORMATTERS.get(language)


def _config_dirs(path: Path) -> list[Path]:
    """The file's directory up to (and including) the project root."""
    start = path.resolve().parent
    root = project_root(start)
    dirs = [start]
    if start != root:
        for parent in start.parents:
            dirs.append(parent)
            if parent == root:
                break
    return dirs


def _find_python_formatter(directory: Path):
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        try:
            tools = tomllib.loads(
                pyproject.read_text(encoding="utf-8")
            ).get("tool", {})
        except (OSError, ValueError):
            tools = {}
        if "black" in tools:
            return "black"
        if "ruff" in tools:
            return "ruff"
    if any((directory / name).is_file() for name in ("ruff.toml", ".ruff.toml")):
        return "ruff"
    return None


def _find_javascript_formatter(directory: Path):
    if _has_prettier_config(directory):
        return "prettier"
    if any((directory / name).is_file() for name in _BIOME_FILES):
        return "biome"
    return None


def _find_css_formatter(directory: Path):
    # Prettier is the only packaged CSS formatter; stylelint --fix is an
    # autofix, not a formatter, and CSS has no unconfigured default.
    return "prettier" if _has_prettier_config(directory) else None


def _find_rust_formatter(directory: Path):
    if any((directory / name).is_file() for name in _RUSTFMT_FILES):
        return "rustfmt"
    return None


def _has_prettier_config(directory: Path) -> bool:
    if any((directory / name).is_file() for name in _PRETTIER_FILES):
        return True
    package_json = directory / "package.json"
    if not package_json.is_file():
        return False
    try:
        manifest = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(manifest, dict) and "prettier" in manifest


_CONFIG_FINDERS = {
    "python": _find_python_formatter,
    "javascript": _find_javascript_formatter,
    "css": _find_css_formatter,
    "rust": _find_rust_formatter,
}

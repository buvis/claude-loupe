"""Behavioral matrix for record_read.py, guard_edit.py, allow_edit.py.

Drives the REAL scripts with synthetic hook JSON via subprocess, the way
Claude Code invokes them, against an isolated HOME. Rows mirror the PRD's
critical scenarios: two partial reads then a full-file edit is allowed,
an unread edit blocks only under ``read_guard: block``, and
``/loupe-allow-edit`` overrides exactly one edit.

The default mode is ``warn``, so the default-config rows assert an
allowed edit plus a stderr notice - a guard that blocked by default would
false-positive on every edit informed by Grep output or a subagent, which
is the reason the default is what it is.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe.project import project_hash

HOOKS_DIR = Path(__file__).resolve().parents[1]

SOURCE = "\n".join(f"line {n}" for n in range(1, 51)) + "\n"


class ReadGuardHarness(unittest.TestCase):
    """Isolated HOME plus helpers to run the real hook scripts."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.project = self.home / "proj"
        (self.project / ".git").mkdir(parents=True)
        self.target = self.project / "app.py"
        self.target.write_text(SOURCE, encoding="utf-8")

    def env(self) -> dict:
        return {"HOME": str(self.home), "PATH": os.environ.get("PATH", "")}

    def run_hook(self, script: str, payload):
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script)],
            input=json.dumps(payload),
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def run_helper(self, script: str, *args):
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script), *args],
            cwd=str(self.project),
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=60,
        )

    def set_mode(self, mode: str, **extra) -> None:
        config = self.project / ".claude"
        config.mkdir(parents=True, exist_ok=True)
        (config / "loupe.json").write_text(
            json.dumps({"read_guard": mode, **extra}), encoding="utf-8"
        )

    def read_payload(self, offset=None, limit=None, path=None) -> dict:
        tool_input = {"file_path": str(path or self.target)}
        if offset is not None:
            tool_input["offset"] = offset
        if limit is not None:
            tool_input["limit"] = limit
        return {
            "session_id": "s1",
            "hook_event_name": "PostToolUse",
            "cwd": str(self.project),
            "tool_name": "Read",
            "tool_input": tool_input,
        }

    def edit_payload(self, old_string: str, path=None) -> dict:
        return {
            "session_id": "s1",
            "hook_event_name": "PreToolUse",
            "cwd": str(self.project),
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(path or self.target),
                "old_string": old_string,
                "new_string": "replaced",
            },
        }

    def state_file(self) -> Path:
        return (
            self.home
            / ".claude"
            / "loupe"
            / "state"
            / f"{project_hash(self.project)}.json"
        )

    def state(self) -> dict:
        return json.loads(self.state_file().read_text(encoding="utf-8"))

    def ranges(self) -> list:
        return self.state()["runtime"]["read_ranges"][str(self.target)]


class RecordReadTests(ReadGuardHarness):
    def test_whole_file_read_records_full_coverage(self) -> None:
        result = self.run_hook("record_read.py", self.read_payload())
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.ranges()[0][0], 1)

    def test_partial_read_records_its_span(self) -> None:
        self.run_hook("record_read.py", self.read_payload(offset=10, limit=5))
        self.assertEqual(self.ranges(), [[10, 14]])

    def test_two_adjacent_partial_reads_coalesce(self) -> None:
        """PRD scenario: reads of 1-100 and 101-200 must merge into one."""
        self.run_hook("record_read.py", self.read_payload(offset=1, limit=100))
        self.run_hook("record_read.py", self.read_payload(offset=101, limit=100))
        self.assertEqual(self.ranges(), [[1, 200]])

    def test_non_read_tool_is_ignored(self) -> None:
        """Ignoring means writing nothing at all - not writing an empty entry."""
        payload = {**self.read_payload(), "tool_name": "Write"}
        self.assertEqual(self.run_hook("record_read.py", payload).returncode, 0)
        self.assertFalse(self.state_file().exists())

    def test_malformed_payload_exits_zero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOKS_DIR / "record_read.py")],
            input="not json",
            env=self.env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0)


class GuardEditTests(ReadGuardHarness):
    def test_unread_edit_warns_but_allows_by_default(self) -> None:
        result = self.run_hook("guard_edit.py", self.edit_payload("line 30"))
        self.assertEqual(result.returncode, 0)
        self.assertIn("read guard (warning)", result.stderr)

    def test_unread_edit_blocks_in_block_mode(self) -> None:
        self.set_mode("block")
        result = self.run_hook("guard_edit.py", self.edit_payload("line 30"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("were not read this session", result.stderr)
        self.assertIn("/loupe-allow-edit", result.stderr)

    def test_read_then_edit_is_silent(self) -> None:
        self.set_mode("block")
        self.run_hook("record_read.py", self.read_payload())
        result = self.run_hook("guard_edit.py", self.edit_payload("line 30"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_partial_reads_then_full_file_write_is_allowed(self) -> None:
        """PRD scenario: 1-25 and 26-50 read, then a whole-file Write."""
        self.set_mode("block")
        self.run_hook("record_read.py", self.read_payload(offset=1, limit=25))
        self.run_hook("record_read.py", self.read_payload(offset=26, limit=25))
        payload = {
            **self.edit_payload("line 1"),
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.target), "content": "new"},
        }
        self.assertEqual(self.run_hook("guard_edit.py", payload).returncode, 0)

    def test_off_mode_skips_entirely(self) -> None:
        self.set_mode("off")
        result = self.run_hook("guard_edit.py", self.edit_payload("line 30"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_markdown_is_exempt(self) -> None:
        self.set_mode("block")
        doc = self.project / "CHANGELOG.md"
        doc.write_text("# Changelog\n\n- entry\n", encoding="utf-8")
        result = self.run_hook("guard_edit.py", self.edit_payload("- entry", path=doc))
        self.assertEqual(result.returncode, 0)

    def test_new_file_is_exempt(self) -> None:
        self.set_mode("block")
        payload = {
            **self.edit_payload("x"),
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(self.project / "brand_new.py"),
                "content": "print(1)\n",
            },
        }
        self.assertEqual(self.run_hook("guard_edit.py", payload).returncode, 0)

    def test_unresolvable_target_never_blocks(self) -> None:
        """old_string absent from the file: defer, never guess a block."""
        self.set_mode("block")
        result = self.run_hook("guard_edit.py", self.edit_payload("nowhere in file"))
        self.assertEqual(result.returncode, 0)

    def test_multiedit_blocks_on_any_uncovered_span(self) -> None:
        self.set_mode("block")
        self.run_hook("record_read.py", self.read_payload(offset=1, limit=5))
        payload = {
            **self.edit_payload("x"),
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(self.target),
                "edits": [
                    {"old_string": "line 3", "new_string": "a"},
                    {"old_string": "line 40", "new_string": "b"},
                ],
            },
        }
        result = self.run_hook("guard_edit.py", payload)
        self.assertEqual(result.returncode, 2)
        self.assertIn("40-40", result.stderr)

    def test_disabled_project_skips(self) -> None:
        self.set_mode("block", enabled=False)
        self.assertEqual(
            self.run_hook("guard_edit.py", self.edit_payload("line 30")).returncode, 0
        )

    def test_invalid_mode_falls_back_to_warn(self) -> None:
        self.set_mode("nonsense")
        result = self.run_hook("guard_edit.py", self.edit_payload("line 30"))
        self.assertEqual(result.returncode, 0)
        self.assertIn("read guard (warning)", result.stderr)


class AllowEditOverrideTests(ReadGuardHarness):
    def test_override_permits_exactly_one_edit(self) -> None:
        self.set_mode("block")
        self.assertEqual(self.run_helper("allow_edit.py", str(self.target)).returncode, 0)

        first = self.run_hook("guard_edit.py", self.edit_payload("line 30"))
        self.assertEqual(first.returncode, 0, "the override should cover this edit")

        second = self.run_hook("guard_edit.py", self.edit_payload("line 30"))
        self.assertEqual(second.returncode, 2, "the override must be spent")

    def test_grant_records_the_absolute_path(self) -> None:
        self.run_helper("allow_edit.py", str(self.target))
        self.assertEqual(self.state()["runtime"]["allow_edit"], [str(self.target)])

    def test_duplicate_grant_is_reported_not_stacked(self) -> None:
        self.run_helper("allow_edit.py", str(self.target))
        result = self.run_helper("allow_edit.py", str(self.target))
        self.assertEqual(result.returncode, 0)
        self.assertIn("already pending", result.stdout)
        self.assertEqual(len(self.state()["runtime"]["allow_edit"]), 1)

    def test_missing_file_is_refused(self) -> None:
        result = self.run_helper("allow_edit.py", str(self.project / "nope.py"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("not an existing file", result.stderr)

    def test_no_argument_is_a_usage_error(self) -> None:
        result = self.run_helper("allow_edit.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Behavioral test matrix for the four loupe hook entry points.

Drives the REAL scripts with synthetic hook JSON via subprocess - the
way Claude Code invokes them - against an isolated HOME and PATH. Rows
mirror the PRD success metrics: planted secret blocks, stub blocks,
security violation blocks, advisory renders inline, Stop drains the
queue exactly once, a missing tool nudges exactly once per project,
disabled projects and malformed input exit 0, and a poisoned engine
fails open.

Where a row needs ast-grep, a planted fake binary replays canned
matches carrying real rule-pack ids over real rule-pack fixture content
(the pack itself is verified against the real binary in
test_rulepack.py); a gated class re-proves the blocking rows against
the real binary whenever it is installed.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe.project import project_hash

HOOKS_DIR = Path(__file__).resolve().parents[1]
FIXTURES_DIR = HOOKS_DIR.parent / "rules" / "ast-grep" / "fixtures"

STUB_RULE = "stub-python-pass-only-body"
SECURITY_RULE = "security-python-eval-exec"
ADVISORY_RULE = "correctness-python-mutable-default-arg"

# Synthetic AWS-shaped key: matches the scanner, is not a credential.
PLANTED_SECRET = 'AWS_ACCESS_KEY_ID = "AKIAJRXJVQMLCWEWJQGA"\n'


def canned_matches(rule_id: str, severity: str = "error") -> str:
    return json.dumps(
        [
            {
                "ruleId": rule_id,
                "severity": severity,
                "message": "canned rule-pack match",
                "range": {"start": {"line": 0, "column": 0}},
            }
        ]
    )


class EntryPointHarness(unittest.TestCase):
    """Isolated HOME/PATH plus helpers to run the real hook scripts."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.bin_dir = self.home / "bin"
        self.bin_dir.mkdir()
        self.project = self.home / "proj"
        (self.project / ".git").mkdir(parents=True)
        self.extra_path_dirs: list = []

    def run_hook(self, script: str, payload=None, stdin_text=None):
        path_dirs = [str(self.bin_dir), *map(str, self.extra_path_dirs)]
        return subprocess.run(
            [sys.executable, str(HOOKS_DIR / script)],
            input=json.dumps(payload) if stdin_text is None else stdin_text,
            env={"HOME": str(self.home), "PATH": os.pathsep.join(path_dirs)},
            capture_output=True,
            text=True,
            timeout=60,
        )

    def plant_executable(self, name: str, body: str) -> Path:
        path = self.bin_dir / name
        path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        os.chmod(path, 0o755)
        return path

    def plant_astgrep(self, payload: str = "[]") -> None:
        self.plant_executable(
            "ast-grep", f"import sys\nsys.stdout.write({payload!r})\n"
        )

    def write_payload(self, file_path: Path, content=None) -> dict:
        if content is None:
            content = file_path.read_text(encoding="utf-8")
        return {
            "session_id": "s1",
            "hook_event_name": "PostToolUse",
            "cwd": str(self.project),
            "tool_name": "Write",
            "tool_input": {"file_path": str(file_path), "content": content},
        }

    def stop_payload(self) -> dict:
        return {
            "session_id": "s1",
            "hook_event_name": "Stop",
            "cwd": str(self.project),
            "stop_hook_active": False,
        }

    def state_path(self) -> Path:
        name = f"{project_hash(self.project)}.json"
        return self.home / ".claude" / "loupe" / "state" / name

    def read_state(self) -> dict:
        return json.loads(self.state_path().read_text(encoding="utf-8"))

    def analyze_fixture(self, rule_id: str, file_name: str, severity="error"):
        """Run analyze.py over real fixture content with a canned match."""
        fixture = FIXTURES_DIR / rule_id / "positive.py"
        target = self.project / file_name
        target.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
        self.plant_astgrep(canned_matches(rule_id, severity))
        return self.run_hook("analyze.py", self.write_payload(target)), target


class SecretsRowTests(EntryPointHarness):
    def test_planted_secret_aborts_the_write(self) -> None:
        target = self.project / "settings.py"
        payload = {
            "session_id": "s1",
            "hook_event_name": "PreToolUse",
            "cwd": str(self.project),
            "tool_name": "Write",
            "tool_input": {"file_path": str(target), "content": PLANTED_SECRET},
        }
        result = self.run_hook("scan_secrets.py", payload)
        self.assertEqual(result.returncode, 2)
        self.assertIn("aws-access-key", result.stderr)
        self.assertIn("settings.py", result.stderr)

    def test_multiedit_new_strings_are_scanned(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "cwd": str(self.project),
            "tool_name": "MultiEdit",
            "tool_input": {
                "file_path": str(self.project / "conf.py"),
                "edits": [
                    {"old_string": "a", "new_string": "b = 1"},
                    {"old_string": "x", "new_string": PLANTED_SECRET},
                ],
            },
        }
        result = self.run_hook("scan_secrets.py", payload)
        self.assertEqual(result.returncode, 2)
        self.assertIn("aws-access-key", result.stderr)

    def test_clean_content_passes_silently(self) -> None:
        payload = {
            "hook_event_name": "PreToolUse",
            "cwd": str(self.project),
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(self.project / "app.py"),
                "old_string": "a",
                "new_string": "def add(a, b):\n    return a + b\n",
            },
        }
        result = self.run_hook("scan_secrets.py", payload)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


class BlockingRowTests(EntryPointHarness):
    def test_stub_edit_blocks_naming_file_rule_and_line(self) -> None:
        result, target = self.analyze_fixture(STUB_RULE, "sync.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn(str(target), result.stderr)
        self.assertIn(STUB_RULE, result.stderr)
        self.assertIn("line 1", result.stderr)

    def test_security_violation_blocks(self) -> None:
        result, target = self.analyze_fixture(SECURITY_RULE, "runner.py")
        self.assertEqual(result.returncode, 2)
        self.assertIn(SECURITY_RULE, result.stderr)

    def test_blocking_findings_still_land_in_session_state(self) -> None:
        self.analyze_fixture(STUB_RULE, "sync.py")
        categories = [
            finding["category"]
            for finding in self.read_state()["runtime"]["findings"]
        ]
        self.assertIn("stub", categories)


class AdvisoryRowTests(EntryPointHarness):
    def test_advisory_finding_prints_inline_and_passes(self) -> None:
        result, target = self.analyze_fixture(
            ADVISORY_RULE, "widgets.py", severity="warning"
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn(ADVISORY_RULE, result.stdout)
        self.assertIn("advisory", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_advisory_file_is_queued_for_stop(self) -> None:
        _, target = self.analyze_fixture(
            ADVISORY_RULE, "widgets.py", severity="warning"
        )
        self.assertIn(str(target), self.read_state()["runtime"]["format_queue"])


class StopOnceRowTests(EntryPointHarness):
    def test_stop_runs_deferred_fix_and_format_exactly_once(self) -> None:
        target = self.project / "app.py"
        target.write_text("x = 1\n", encoding="utf-8")
        self.plant_astgrep("[]")
        analyzed = self.run_hook("analyze.py", self.write_payload(target))
        self.assertEqual(analyzed.returncode, 0)

        # Fake ruff appends one marker line per invocation, so a second
        # Stop that ran anything would visibly change the file again.
        self.plant_executable(
            "ruff",
            "import sys\n"
            "with open(sys.argv[-1], 'a') as fh:\n"
            "    fh.write('# loupe-touched\\n')\n",
        )
        first = self.run_hook("agent_end.py", self.stop_payload())
        self.assertEqual(first.returncode, 0)
        self.assertIn("loupe stop summary", first.stdout)
        self.assertIn("autofix ruff (changed)", first.stdout)
        self.assertIn("format ruff (changed)", first.stdout)
        settled = target.read_text(encoding="utf-8")

        second = self.run_hook("agent_end.py", self.stop_payload())
        self.assertEqual(second.returncode, 0)
        self.assertEqual(second.stdout, "")
        self.assertEqual(target.read_text(encoding="utf-8"), settled)


class NudgeOnceRowTests(EntryPointHarness):
    def test_missing_tool_nudge_fires_exactly_once_per_project(self) -> None:
        target = self.project / "deploy.sh"
        target.write_text("echo hi\n", encoding="utf-8")
        analyzed = self.run_hook("analyze.py", self.write_payload(target))
        self.assertEqual(analyzed.returncode, 0)

        first = self.run_hook("agent_end.py", self.stop_payload())
        self.assertIn("shellcheck", first.stdout)
        self.assertIn("once per project", first.stdout)

        second = self.run_hook("agent_end.py", self.stop_payload())
        self.assertEqual(second.stdout, "")

        # A later turn in the same project must not re-print the nudge.
        target2 = self.project / "roll.sh"
        target2.write_text("echo bye\n", encoding="utf-8")
        self.run_hook("analyze.py", self.write_payload(target2))
        third = self.run_hook("agent_end.py", self.stop_payload())
        self.assertNotIn("shellcheck", third.stdout)


class DisabledRowTests(EntryPointHarness):
    def setUp(self) -> None:
        super().setUp()
        override = self.project / ".claude" / "loupe.json"
        override.parent.mkdir(parents=True)
        override.write_text('{"enabled": false}', encoding="utf-8")
        self.marker = self.home / "astgrep-ran"
        self.plant_executable(
            "ast-grep",
            f"import sys\nopen({str(self.marker)!r}, 'w').write('ran')\n"
            "sys.stdout.write('[]')\n",
        )

    def test_all_four_hooks_exit_zero_silently_when_disabled(self) -> None:
        target = self.project / "sync.py"
        target.write_text("def f():\n    pass\n", encoding="utf-8")
        rows = (
            ("session_start.py", {"cwd": str(self.project), "source": "startup"}),
            (
                "scan_secrets.py",
                {
                    "cwd": str(self.project),
                    "tool_name": "Write",
                    "tool_input": {
                        "file_path": str(target),
                        "content": PLANTED_SECRET,
                    },
                },
            ),
            ("analyze.py", self.write_payload(target)),
            ("agent_end.py", self.stop_payload()),
        )
        for script, payload in rows:
            with self.subTest(script=script):
                result = self.run_hook(script, payload)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")
                self.assertEqual(result.stderr, "")
        self.assertFalse(self.state_path().exists())
        self.assertFalse(self.marker.exists())


class MalformedInputRowTests(EntryPointHarness):
    def test_malformed_hook_json_exits_zero_for_all_hooks(self) -> None:
        for script in (
            "session_start.py",
            "scan_secrets.py",
            "analyze.py",
            "agent_end.py",
        ):
            for bad in ("{{{ not json", "", "[1, 2]", "null"):
                with self.subTest(script=script, stdin=bad or "<empty>"):
                    result = self.run_hook(script, stdin_text=bad)
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(result.stderr, "")

    def test_unknown_fields_exit_zero(self) -> None:
        result = self.run_hook(
            "scan_secrets.py", {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        )
        self.assertEqual(result.returncode, 0)
        result = self.run_hook("analyze.py", {"tool_name": "Write", "tool_input": {}})
        self.assertEqual(result.returncode, 0)


class FailOpenRowTests(EntryPointHarness):
    """A poisoned engine (state layer cannot persist) never breaks a hook."""

    def _poison_state_dir(self) -> None:
        loupe_dir = self.home / ".claude" / "loupe"
        loupe_dir.mkdir(parents=True)
        # A FILE where the state directory belongs: save_state's mkdir
        # raises, proving the fail-open wrapper through the real script.
        (loupe_dir / "state").write_text("poison", encoding="utf-8")

    def test_analyze_fails_open_when_state_cannot_persist(self) -> None:
        self._poison_state_dir()
        target = self.project / "app.py"
        target.write_text("x = 1\n", encoding="utf-8")
        self.plant_astgrep("[]")
        result = self.run_hook("analyze.py", self.write_payload(target))
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_session_start_fails_open_when_state_cannot_persist(self) -> None:
        self._poison_state_dir()
        result = self.run_hook(
            "session_start.py", {"cwd": str(self.project), "source": "startup"}
        )
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)

    def test_agent_end_fails_open_when_claim_save_fails(self) -> None:
        target = self.project / "app.py"
        target.write_text("x = 1\n", encoding="utf-8")
        state_dir = self.state_path().parent
        state_dir.mkdir(parents=True)
        state = {
            "version": 1,
            "runtime": {"format_queue": [str(target)], "findings": []},
            "persistent": {"nudged": [], "nudge_reported": []},
        }
        self.state_path().write_text(json.dumps(state), encoding="utf-8")
        os.chmod(state_dir, 0o555)
        self.addCleanup(os.chmod, state_dir, 0o755)

        result = self.run_hook("agent_end.py", self.stop_payload())
        self.assertEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)


@unittest.skipIf(
    shutil.which("ast-grep") is None,
    "ast-grep unavailable; blocking rows proven via the canned binary",
)
class RealAstGrepRowTests(EntryPointHarness):
    """Re-prove the blocking rows through the real binary when present."""

    def setUp(self) -> None:
        super().setUp()
        self.extra_path_dirs = [Path(shutil.which("ast-grep")).parent]

    def test_stub_fixture_blocks_through_the_real_binary(self) -> None:
        fixture = FIXTURES_DIR / STUB_RULE / "positive.py"
        target = self.project / "sync.py"
        target.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
        result = self.run_hook("analyze.py", self.write_payload(target))
        self.assertEqual(result.returncode, 2)
        self.assertIn(STUB_RULE, result.stderr)

    def test_security_fixture_blocks_through_the_real_binary(self) -> None:
        fixture = FIXTURES_DIR / SECURITY_RULE / "positive.py"
        target = self.project / "runner.py"
        target.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
        result = self.run_hook("analyze.py", self.write_payload(target))
        self.assertEqual(result.returncode, 2)
        self.assertIn(SECURITY_RULE, result.stderr)


if __name__ == "__main__":
    unittest.main()

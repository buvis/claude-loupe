"""In-process branch coverage for the four hook entry points.

test_entrypoints.py proves the exit-code contract end to end through
real subprocesses, which coverage cannot see. These tests import the
scripts as modules and call main() directly - with stdin, HOME, and
PATH patched - so every branch is measured and engine failures can be
injected precisely with monkeypatching (the fail-open proof).
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import agent_end
import analyze
import scan_secrets
import session_start
from loupe import state as state_mod
from loupe.project import project_hash


class InProcessTestCase(unittest.TestCase):
    """Isolated HOME/PATH; run a hook module's main() with stdin patched."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.bin_dir = self.home / "bin"
        self.bin_dir.mkdir()
        env = mock.patch.dict(
            os.environ, {"HOME": str(self.home), "PATH": str(self.bin_dir)}
        )
        env.start()
        self.addCleanup(env.stop)
        self.project = self.home / "proj"
        (self.project / ".git").mkdir(parents=True)

    def call(self, module, payload=None, stdin_text=None):
        text = json.dumps(payload) if stdin_text is None else stdin_text
        stdout, stderr = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(text)):
            with contextlib.redirect_stdout(stdout):
                with contextlib.redirect_stderr(stderr):
                    code = module.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def plant_executable(self, name: str, body: str) -> Path:
        path = self.bin_dir / name
        path.write_text(f"#!{sys.executable}\n{body}", encoding="utf-8")
        os.chmod(path, 0o755)
        return path

    def plant_astgrep(self, matches) -> None:
        payload = json.dumps(matches)
        self.plant_executable(
            "ast-grep", f"import sys\nsys.stdout.write({payload!r})\n"
        )

    def seed_state(self, runtime=None, persistent=None) -> None:
        state = state_mod.default_state()
        state["runtime"].update(runtime or {})
        state["persistent"].update(persistent or {})
        state_mod.save_state(project_hash(self.project), state)

    def load_state(self) -> dict:
        return state_mod.load_state(project_hash(self.project))

    def disable_project(self) -> None:
        override = self.project / ".claude" / "loupe.json"
        override.parent.mkdir(parents=True, exist_ok=True)
        override.write_text('{"enabled": false}', encoding="utf-8")

    def write_payload(self, target: Path) -> dict:
        return {
            "cwd": str(self.project),
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(target),
                "content": target.read_text(encoding="utf-8"),
            },
        }

    def stop_payload(self) -> dict:
        return {"cwd": str(self.project), "stop_hook_active": False}


class SessionStartTests(InProcessTestCase):
    def test_startup_resets_runtime_and_prints_nothing(self) -> None:
        self.seed_state(runtime={"format_queue": ["stale.py"]})
        code, out, err = self.call(
            session_start, {"cwd": str(self.project), "source": "startup"}
        )
        self.assertEqual((code, out, err), (0, "", ""))
        self.assertEqual(self.load_state()["runtime"]["format_queue"], [])

    def test_resume_resets_runtime(self) -> None:
        self.seed_state(runtime={"format_queue": ["stale.py"]})
        code, _, _ = self.call(
            session_start, {"cwd": str(self.project), "source": "resume"}
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.load_state()["runtime"]["format_queue"], [])

    def test_compact_keeps_the_turns_queue(self) -> None:
        self.seed_state(runtime={"format_queue": ["inflight.py"]})
        code, _, _ = self.call(
            session_start, {"cwd": str(self.project), "source": "compact"}
        )
        self.assertEqual(code, 0)
        self.assertEqual(
            self.load_state()["runtime"]["format_queue"], ["inflight.py"]
        )

    def test_disabled_project_is_untouched(self) -> None:
        self.disable_project()
        self.seed_state(runtime={"format_queue": ["kept.py"]})
        code, _, _ = self.call(
            session_start, {"cwd": str(self.project), "source": "startup"}
        )
        self.assertEqual(code, 0)
        self.assertEqual(self.load_state()["runtime"]["format_queue"], ["kept.py"])

    def test_poisoned_engine_fails_open(self) -> None:
        with mock.patch("loupe.state.load_state", side_effect=RuntimeError):
            code, out, err = self.call(
                session_start, {"cwd": str(self.project), "source": "startup"}
            )
        self.assertEqual((code, out, err), (0, "", ""))


class ScanSecretsTests(InProcessTestCase):
    SECRET = 'AWS_ACCESS_KEY_ID = "AKIAJRXJVQMLCWEWJQGA"'

    def test_edit_new_string_with_secret_blocks(self) -> None:
        code, _, err = self.call(
            scan_secrets,
            {
                "cwd": str(self.project),
                "tool_name": "Edit",
                "tool_input": {
                    "file_path": str(self.project / "conf.py"),
                    "old_string": "x",
                    "new_string": self.SECRET,
                },
            },
        )
        self.assertEqual(code, 2)
        self.assertIn("aws-access-key", err)

    def test_non_write_tool_passes(self) -> None:
        code, _, _ = self.call(
            scan_secrets,
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        )
        self.assertEqual(code, 0)

    def test_missing_tool_input_passes(self) -> None:
        code, _, _ = self.call(scan_secrets, {"tool_name": "Write"})
        self.assertEqual(code, 0)

    def test_non_string_content_passes(self) -> None:
        code, _, _ = self.call(
            scan_secrets,
            {"tool_name": "Write", "tool_input": {"content": 42}},
        )
        self.assertEqual(code, 0)

    def test_multiedit_with_malformed_edits_passes(self) -> None:
        code, _, _ = self.call(
            scan_secrets,
            {"tool_name": "MultiEdit", "tool_input": {"edits": "nope"}},
        )
        self.assertEqual(code, 0)

    def test_poisoned_engine_fails_open(self) -> None:
        with mock.patch(
            "loupe.secrets.scan_for_secrets", side_effect=RuntimeError
        ):
            code, out, err = self.call(
                scan_secrets,
                {
                    "cwd": str(self.project),
                    "tool_name": "Write",
                    "tool_input": {
                        "file_path": "x.py",
                        "content": self.SECRET,
                    },
                },
            )
        self.assertEqual((code, out, err), (0, "", ""))


class AnalyzeTests(InProcessTestCase):
    def _target(self, name: str, content: str) -> Path:
        target = self.project / name
        target.write_text(content, encoding="utf-8")
        return target

    def test_unknown_language_skips_before_any_engine_work(self) -> None:
        target = self._target("blob.xyz", "opaque\n")
        code, out, _ = self.call(analyze, self.write_payload(target))
        self.assertEqual((code, out), (0, ""))
        self.assertFalse(
            (self.home / ".claude" / "loupe" / "state").exists()
        )

    def test_markdown_queues_silently_with_no_findings(self) -> None:
        # A known language with no analyzer: queued for Stop, no output.
        target = self._target("notes.md", "# notes\n")
        code, out, _ = self.call(analyze, self.write_payload(target))
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(
            self.load_state()["runtime"]["format_queue"], [str(target)]
        )

    def test_markdown_only_queue_stays_silent_at_stop(self) -> None:
        # No fixer or formatter handles markdown: the Stop must not
        # print an all-skipped "nothing to do" line every turn.
        target = self._target("notes.md", "# notes\n")
        self.seed_state(runtime={"format_queue": [str(target)]})
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(self.load_state()["runtime"]["format_queue"], [])

    def test_missing_file_passes(self) -> None:
        payload = {
            "cwd": str(self.project),
            "tool_name": "Write",
            "tool_input": {"file_path": str(self.project / "ghost.py")},
        }
        code, _, _ = self.call(analyze, payload)
        self.assertEqual(code, 0)

    def test_advisory_finding_queues_and_records(self) -> None:
        target = self._target("app.py", "x = 1\n")
        self.plant_astgrep(
            [
                {
                    "ruleId": "style-python-demo",
                    "severity": "warning",
                    "message": "demo advisory",
                    "range": {"start": {"line": 0, "column": 0}},
                }
            ]
        )
        code, out, err = self.call(analyze, self.write_payload(target))
        self.assertEqual(code, 0)
        self.assertIn("style-python-demo", out)
        self.assertEqual(err, "")
        state = self.load_state()
        self.assertEqual(state["runtime"]["format_queue"], [str(target)])
        self.assertEqual(len(state["runtime"]["findings"]), 1)

    def test_blocking_finding_exits_two_with_detail(self) -> None:
        target = self._target("app.py", "def f():\n    pass\n")
        self.plant_astgrep(
            [
                {
                    "ruleId": "stub-python-pass-only-body",
                    "severity": "error",
                    "message": "stub body",
                    "range": {"start": {"line": 0, "column": 0}},
                }
            ]
        )
        code, _, err = self.call(analyze, self.write_payload(target))
        self.assertEqual(code, 2)
        self.assertIn("stub-python-pass-only-body", err)
        self.assertIn("line 1", err)
        self.assertIn(str(target), err)

    def test_immediate_fix_runs_inline_instead_of_queuing(self) -> None:
        override = self.project / ".claude" / "loupe.json"
        override.parent.mkdir(parents=True)
        override.write_text('{"immediate_fix": true}', encoding="utf-8")
        target = self._target("app.py", "x = 1\n")
        self.plant_astgrep([])
        self.plant_executable(
            "ruff",
            "import sys\n"
            "with open(sys.argv[-1], 'a') as fh:\n"
            "    fh.write('# fixed\\n')\n",
        )
        code, out, _ = self.call(analyze, self.write_payload(target))
        self.assertEqual(code, 0)
        self.assertIn("loupe immediate fix", out)
        self.assertIn("# fixed", target.read_text(encoding="utf-8"))
        self.assertEqual(self.load_state()["runtime"]["format_queue"], [])

    def test_repeat_edit_does_not_duplicate_queue_entry(self) -> None:
        target = self._target("app.py", "x = 1\n")
        self.plant_astgrep([])
        self.call(analyze, self.write_payload(target))
        self.call(analyze, self.write_payload(target))
        self.assertEqual(
            self.load_state()["runtime"]["format_queue"], [str(target)]
        )

    def test_poisoned_engine_fails_open(self) -> None:
        target = self._target("app.py", "x = 1\n")
        with mock.patch("loupe.astgrep.run_astgrep", side_effect=RuntimeError):
            code, out, err = self.call(analyze, self.write_payload(target))
        self.assertEqual((code, out, err), (0, "", ""))


class AgentEndTests(InProcessTestCase):
    def test_empty_state_prints_nothing(self) -> None:
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual((code, out), (0, ""))

    def test_vanished_queued_file_is_skipped_but_claimed(self) -> None:
        self.seed_state(runtime={"format_queue": [str(self.project / "gone.py")]})
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(self.load_state()["runtime"]["format_queue"], [])

    def test_clippy_runs_once_per_turn_for_queued_rust(self) -> None:
        (self.project / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
        src = self.project / "src"
        src.mkdir()
        first_rs = src / "main.rs"
        second_rs = src / "lib.rs"
        first_rs.write_text("fn main() {}\n", encoding="utf-8")
        second_rs.write_text("pub fn lib() {}\n", encoding="utf-8")
        marker = self.home / "cargo-calls"
        self.plant_executable(
            "cargo",
            "import sys\n"
            f"with open({str(marker)!r}, 'a') as fh:\n"
            "    fh.write(' '.join(sys.argv[1:]) + '\\n')\n"
            "sys.stdout.write('warning: unused variable x\\n')\n",
        )
        self.seed_state(
            runtime={"format_queue": [str(first_rs), str(second_rs)]}
        )
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual(code, 0)
        self.assertIn("slow lint (clippy), advisory:", out)
        self.assertIn("warning: unused variable x", out)
        calls = marker.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0].startswith("clippy"))

    def test_missing_cargo_records_a_clippy_nudge(self) -> None:
        rust = self.project / "main.rs"
        rust.write_text("fn main() {}\n", encoding="utf-8")
        self.seed_state(runtime={"format_queue": [str(rust)]})
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual(code, 0)
        self.assertNotIn("slow lint", out)
        self.assertIn("clippy", self.load_state()["persistent"]["nudged"])

        # The next Stop delivers that nudge exactly once.
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual(code, 0)
        self.assertIn("nudge: 'clippy'", out)
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual(out, "")

    def test_rust_file_outside_a_crate_skips_clippy(self) -> None:
        rust = self.project / "loose.rs"
        rust.write_text("fn main() {}\n", encoding="utf-8")
        marker = self.home / "cargo-calls"
        self.plant_executable(
            "cargo",
            f"open({str(marker)!r}, 'w').write('ran')\n",
        )
        self.seed_state(runtime={"format_queue": [str(rust)]})
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual(code, 0)
        self.assertNotIn("slow lint", out)
        self.assertFalse(marker.exists())

    def test_svelte_check_runs_from_the_project_root(self) -> None:
        component = self.project / "App.svelte"
        component.write_text("<script></script>\n", encoding="utf-8")
        self.plant_executable(
            "svelte-check",
            "import sys\nsys.stdout.write('svelte-check found 0 errors\\n')\n",
        )
        self.seed_state(runtime={"format_queue": [str(component)]})
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual(code, 0)
        self.assertIn("slow lint (svelte-check), advisory:", out)
        self.assertIn("svelte-check found 0 errors", out)

    def test_clean_slow_lint_reports_clean(self) -> None:
        (self.project / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
        rust = self.project / "main.rs"
        rust.write_text("fn main() {}\n", encoding="utf-8")
        self.plant_executable("cargo", "pass\n")
        self.seed_state(runtime={"format_queue": [str(rust)]})
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual(code, 0)
        self.assertIn("slow lint (clippy): clean", out)

    def test_hung_slow_linter_reports_and_moves_on(self) -> None:
        (self.project / "Cargo.toml").write_text("[package]\n", encoding="utf-8")
        rust = self.project / "main.rs"
        rust.write_text("fn main() {}\n", encoding="utf-8")
        self.plant_executable("cargo", "import time\ntime.sleep(5)\n")
        self.seed_state(runtime={"format_queue": [str(rust)]})
        with mock.patch.object(agent_end, "SLOW_LINTER_TIMEOUT_SECONDS", 0.2):
            code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual(code, 0)
        self.assertIn("slow lint (clippy): did not complete", out)

    def test_disabled_project_leaves_the_queue_alone(self) -> None:
        self.disable_project()
        self.seed_state(runtime={"format_queue": ["kept.py"]})
        code, out, _ = self.call(agent_end, self.stop_payload())
        self.assertEqual((code, out), (0, ""))
        self.assertEqual(self.load_state()["runtime"]["format_queue"], ["kept.py"])

    def test_poisoned_engine_fails_open(self) -> None:
        with mock.patch("loupe.state.load_state", side_effect=RuntimeError):
            code, out, err = self.call(agent_end, self.stop_payload())
        self.assertEqual((code, out, err), (0, "", ""))


if __name__ == "__main__":
    unittest.main()

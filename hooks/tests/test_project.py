"""Tests for hooks/loupe/project.py."""

import string
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from loupe import project


class ProjectRootTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()

    def _make_project(self, name: str, marker: str = "dir") -> Path:
        root = self.base / name
        root.mkdir()
        if marker == "dir":
            (root / ".git").mkdir()
        elif marker == "file":
            (root / ".git").write_text("gitdir: ../elsewhere\n", encoding="utf-8")
        return root

    def test_subdirectory_maps_to_marked_root(self) -> None:
        root = self._make_project("repo")
        deep = root / "src" / "pkg" / "mod"
        deep.mkdir(parents=True)
        self.assertEqual(project.project_root(deep), root)

    def test_git_file_marker_recognized(self) -> None:
        # Worktrees and submodules use a .git *file*, not a directory.
        root = self._make_project("worktree", marker="file")
        sub = root / "src"
        sub.mkdir()
        self.assertEqual(project.project_root(sub), root)

    def test_no_marker_falls_back_to_a_stable_root(self) -> None:
        bare = self.base / "no-repo"
        bare.mkdir()
        result = project.project_root(bare)
        # Either the directory itself (no marker anywhere up the tree) or
        # a genuinely marked ancestor of the temp location.
        self.assertTrue(result == bare or (result / ".git").exists())
        self.assertEqual(result, project.project_root(bare))


class ProjectHashTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()

    def _make_project(self, name: str) -> Path:
        root = self.base / name
        (root / ".git").mkdir(parents=True)
        return root

    def test_same_project_same_hash_across_subdirs(self) -> None:
        root = self._make_project("repo")
        sub = root / "src"
        sub.mkdir()
        self.assertEqual(project.project_hash(root), project.project_hash(sub))

    def test_distinct_projects_distinct_hashes(self) -> None:
        a = self._make_project("alpha")
        b = self._make_project("beta")
        self.assertNotEqual(project.project_hash(a), project.project_hash(b))

    def test_hash_is_stable_and_wellformed(self) -> None:
        root = self._make_project("repo")
        first = project.project_hash(root)
        self.assertEqual(first, project.project_hash(root))
        self.assertEqual(len(first), 12)
        self.assertTrue(all(c in string.hexdigits for c in first))
        self.assertEqual(first, first.lower())

    def test_path_normalization(self) -> None:
        # Dot segments and string inputs hash like the resolved path.
        root = self._make_project("repo")
        sub = root / "src"
        sub.mkdir()
        wobbly = str(sub / ".." / "src")
        self.assertEqual(project.project_hash(wobbly), project.project_hash(sub))


if __name__ == "__main__":
    unittest.main()

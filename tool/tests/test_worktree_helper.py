"""worktree_helper.py の E2E テスト。一時ディレクトリに Git リポジトリを作り、シナリオを順に実行する。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HELPER = (Path(__file__).resolve().parents[2]
          / "skills" / "speckit" / "speckit-worktree" / "scripts" / "worktree_helper.py")
GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
}


class WorktreeHelperScenario(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        self.env = {**os.environ, **GIT_ENV}
        self.git("init", "-q", "-b", "main")
        (self.repo / "docs" / "feature").mkdir(parents=True)
        (self.repo / ".specify").mkdir()
        (self.repo / ".gitignore").write_text(".worktrees/\n", encoding="utf-8")
        (self.repo / ".specify" / ".gitignore").write_text("feature.json\n", encoding="utf-8")
        (self.repo / "docs" / "feature" / "spec_order.md").write_text(
            "- **1. [TODO](./todo-cli.md)**: a\n- **2. [同期](./002-sync.md)**: b\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "init")

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- helpers ---------------------------------------------------------
    def git(self, *args: str, cwd: Path | None = None) -> str:
        return subprocess.run(["git", *args], cwd=cwd or self.repo, env=self.env, check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def run_helper(self, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HELPER), *args], cwd=cwd or self.repo, env=self.env,
                              capture_output=True, text=True, encoding="utf-8")

    def out(self, *args: str, cwd: Path | None = None) -> str:
        proc = self.run_helper(*args, cwd=cwd)
        return (proc.stdout + proc.stderr).strip()

    def code(self, *args: str) -> int:
        return self.run_helper(*args).returncode

    def checkpoints(self, feature: str, steps: str) -> None:
        for step in steps.split():
            proc = self.run_helper("checkpoint", feature, step, f"x: {step}")
            self.assertEqual(proc.returncode, 0, proc.stderr)

    @staticmethod
    def spec_files(worktree: Path, name: str, tasks: str = "- [ ] T001\n") -> None:
        d = worktree / "specs" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "spec.md").write_text("s\n", encoding="utf-8")
        (d / "plan.md").write_text("p\n", encoding="utf-8")
        (d / "tasks.md").write_text(tasks, encoding="utf-8")

    # --- scenario --------------------------------------------------------
    def test_full_lifecycle(self) -> None:
        # 解決と自動検出
        self.assertEqual(self.out("resolve", "1"), "001-todo-cli")
        self.assertEqual(self.out("resolve", "sync"), "002-sync")
        self.assertEqual(self.out("resolve", "002-sync.md"), "002-sync")
        self.assertEqual(self.code("resolve", "9"), 1)
        self.assertEqual(self.out("resolve", "003-new-thing"), "003-new-thing")
        self.assertEqual(self.out("list").splitlines(), ["001-todo-cli", "002-sync"])
        self.assertEqual(self.out("next", "--phase", "spec"), "001-todo-cli")
        self.assertEqual(self.out("next", "--phase", "coding"), "")
        self.assertEqual(self.code("ensure", "1", "--phase", "coding"), 3)

        # 仕様工程
        self.assertIn("WORKTREE_STATE: created", self.out("ensure", "1", "--phase", "spec"))
        w1 = self.repo / ".worktrees" / "001-todo-cli"
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertTrue((w1 / ".specify" / "feature.json").is_file())
        self.spec_files(w1, "001-todo-cli")
        proc = self.run_helper("checkpoint", "1", "S2", "docs(spec): specify", cwd=w1)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("NEXT_STEP: S3", self.out("state", "1", "--phase", "spec", cwd=w1))
        self.assertEqual(self.git("ls-files", ".specify/feature.json", cwd=w1), "")
        self.assertIn("WORKTREE_STATE: reused", self.out("ensure", "1", "--phase", "spec"))
        self.assertEqual(self.code("finish", "1", "--phase", "spec"), 1)
        self.assertEqual(self.code("ensure", "1", "--phase", "coding"), 3)
        self.checkpoints("1", "S3 S4 S5 S6 S7-1 S7-2 S7-3")
        self.assertIn("NEXT_STEP: S12", self.out("state", "1", "--phase", "spec"))
        self.assertIn("NEXT_STEP: S8", self.out("state", "1", "--phase", "all"))
        self.assertEqual(self.out("next", "--phase", "coding"), "001-todo-cli")
        (self.repo / "dirty.txt").write_text("x", encoding="utf-8")
        self.assertEqual(self.code("finish", "1", "--phase", "spec"), 1)
        (self.repo / "dirty.txt").unlink()
        self.assertIn("FINISHED: 001-todo-cli (spec)", self.out("finish", "1", "--phase", "spec"))
        self.assertFalse(w1.exists())
        self.assertEqual(self.git("branch", "--list", "feature/001-todo-cli"), "")
        self.assertEqual(self.git("log", "-1", "--format=%s"), "merge(001-todo-cli): spec")
        self.assertEqual(len(self.git("log", "-1", "--format=%P").split()), 2)
        self.assertEqual(self.code("ensure", "1", "--phase", "spec"), 3)
        self.assertEqual(self.out("next", "--phase", "spec"), "002-sync")
        self.assertEqual(self.out("next", "--phase", "coding"), "001-todo-cli")

        # 実装工程（main から新規作成）
        self.assertIn("WORKTREE_STATE: created", self.out("ensure", "1", "--phase", "coding"))
        self.assertIn("NEXT_STEP: S8", self.out("state", "1", "--phase", "coding"))
        (w1 / "specs" / "001-todo-cli" / "tasks.md").write_text("- [x] T001\n", encoding="utf-8")
        (w1 / "app.txt").write_text("code\n", encoding="utf-8")
        self.checkpoints("1", "S8 S9 S10 S11")
        self.assertIn("FINISHED: 001-todo-cli (coding)", self.out("finish", "1", "--phase", "coding"))
        self.assertEqual(self.code("ensure", "1", "--phase", "coding"), 3)
        self.assertEqual(self.out("next", "--phase", "coding"), "")
        self.assertEqual(self.out("next", "--phase", "all"), "002-sync")

        # 通し（ブランチだけ残った場合の作り直し、main 以外にいるときの finish）
        self.assertIn("WORKTREE_STATE: created", self.out("ensure", "2", "--phase", "all"))
        w2 = self.repo / ".worktrees" / "002-sync"
        self.git("worktree", "remove", "--force", str(w2))
        self.assertIn("WORKTREE_STATE: reattached", self.out("ensure", "2", "--phase", "all"))
        self.spec_files(w2, "002-sync")
        self.checkpoints("2", "S2 S3 S4 S5 S6 S7-1 S7-2 S7-3 S8")
        self.assertEqual(self.code("ensure", "2", "--phase", "spec"), 3)
        self.checkpoints("2", "S9 S10 S11")
        self.git("checkout", "-q", "-b", "other")
        self.assertIn("FINISHED: 002-sync (all)", self.out("finish", "2", "--phase", "all"))
        self.assertEqual(self.git("branch", "--show-current"), "main")
        self.assertIn("| 002-sync | 完了 | 未着手 | - |", self.out("status"))

        # 一覧にない完全名と中止
        self.out("ensure", "003-extra", "--phase", "spec")
        self.assertTrue((self.repo / ".worktrees" / "003-extra").is_dir())
        self.assertIn("確認のみ", self.out("abort", "3"))
        self.assertTrue((self.repo / ".worktrees" / "003-extra").is_dir())
        self.assertIn("ABORTED", self.out("abort", "3", "--yes"))
        self.assertFalse((self.repo / ".worktrees" / "003-extra").exists())

    def test_gitignore_required(self) -> None:
        (self.repo / ".gitignore").write_text("", encoding="utf-8")
        self.git("commit", "-qam", "drop ignore")
        proc = self.run_helper("ensure", "1", "--phase", "spec")
        self.assertEqual(proc.returncode, 1)
        self.assertIn(".worktrees/", proc.stderr)


if __name__ == "__main__":
    unittest.main()

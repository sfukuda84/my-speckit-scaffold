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
        # クラウドセッションの中でテストを実行しても、ローカルの動作を確かめられるようにする。
        for key in ("CLAUDE_CODE_REMOTE", "SPECKIT_MAIN_BRANCH"):
            self.env.pop(key, None)
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
        # 未完了のタスクが残っているので、確認なしにはマージしない
        self.assertEqual(self.code("finish", "2", "--phase", "all"), 3)
        # メインの作業ツリーが main 以外にいるので、確認なしには切り替えない
        self.assertIn("NOT_ON_MAIN", self.out("finish", "2", "--phase", "all", "--allow-unchecked"))
        self.assertIn("FINISHED: 002-sync (all)",
                      self.out("finish", "2", "--phase", "all", "--allow-unchecked", "--switch"))
        self.assertEqual(self.git("branch", "--show-current"), "main")
        # 未完了のタスクが残っていても、実装までマージ済みなら完了として扱い、再び選ばない
        self.assertIn("| 002-sync | 完了 | 完了 | - |", self.out("status"))
        self.assertEqual(self.out("next", "--phase", "all"), "")

        # 一覧にない完全名と中止
        self.out("ensure", "003-extra", "--phase", "spec")
        self.assertTrue((self.repo / ".worktrees" / "003-extra").is_dir())
        self.assertIn("確認のみ", self.out("abort", "3"))
        self.assertTrue((self.repo / ".worktrees" / "003-extra").is_dir())
        self.assertIn("ABORTED", self.out("abort", "3", "--yes"))
        self.assertFalse((self.repo / ".worktrees" / "003-extra").exists())

    def test_finish_rerun_after_conflict_keeps_progress(self) -> None:
        """H1: 競合を手で解消してマージした後に finish を再実行しても、進捗が失われない。"""
        self.out("ensure", "1", "--phase", "all")
        wt = self.repo / ".worktrees" / "001-todo-cli"
        self.spec_files(wt, "001-todo-cli", tasks="- [x] T001\n")
        (wt / "shared.txt").write_text("branch\n", encoding="utf-8")
        self.checkpoints("1", "S2 S3 S4 S5 S6 S7-1 S7-2 S7-3 S8 S9 S10 S11")
        (self.repo / "shared.txt").write_text("main\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "main side change")
        self.assertEqual(self.code("finish", "1", "--phase", "all"), 1)  # 競合
        (self.repo / "shared.txt").write_text("resolved\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "resolve conflict")
        self.assertIn("NEXT_STEP: S12", self.out("state", "1", "--phase", "all"))
        self.assertIn("FINISHED: 001-todo-cli (all)", self.out("finish", "1", "--phase", "all"))
        self.assertEqual(self.out("next", "--phase", "all"), "002-sync")

    def test_next_follows_spec_order(self) -> None:
        """H2: 着手順は番号順ではなく spec_order.md の並びに従う。"""
        (self.repo / "docs" / "feature" / "spec_order.md").write_text(
            "- **0. [基盤](./000-app-basic.md)**\n- **3. [後から](./003-late.md)**\n"
            "- **1. [予約](./001-booking.md)**\n- **999. [運用](./999-app-nfr.md)**\n"
            "- **2. [集計](./002-report.md)**\n", encoding="utf-8")
        self.git("commit", "-qam", "order")
        self.assertEqual(self.out("list").splitlines(),
                         ["000-app-basic", "003-late", "001-booking", "999-app-nfr", "002-report"])
        self.assertEqual(self.out("next", "--phase", "spec"), "000-app-basic")

    def test_finish_refuses_inside_worktree(self) -> None:
        """M1: worktree の中から finish すると止まる。"""
        self.out("ensure", "1", "--phase", "spec")
        wt = self.repo / ".worktrees" / "001-todo-cli"
        self.spec_files(wt, "001-todo-cli")
        self.checkpoints("1", "S2 S3 S4 S5 S6 S7-1 S7-2 S7-3")
        proc = self.run_helper("finish", "1", "--phase", "spec", cwd=wt)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("worktree の外", proc.stderr)
        self.assertTrue(wt.is_dir())

    def test_checkpoint_updates_feature_status(self) -> None:
        """M2: S2 で spec化済み、S11 で 完了 に状態欄と README の一覧を更新する。"""
        fdir = self.repo / "docs" / "feature"
        (fdir / "001-todo-cli.md").write_text(
            "# TODO\n\n**状態**: 未着手 | **区分**: MVP | **想定順序**: 1 | **依存**: —\n", encoding="utf-8")
        (fdir / "README.md").write_text(
            "| # | 機能 | 区分 | 状態 | 依存 | 一言 |\n|---|---|---|---|---|---|\n"
            "| 1 | [TODO](./001-todo-cli.md) | MVP | 未着手 | — | a |\n", encoding="utf-8")
        (fdir / "spec_order.md").write_text("- **1. [TODO](./001-todo-cli.md)**: a\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "feature files")
        self.out("ensure", "1", "--phase", "all")
        wt = self.repo / ".worktrees" / "001-todo-cli"
        self.spec_files(wt, "001-todo-cli", tasks="- [x] T001\n")
        self.checkpoints("1", "S2")
        text = (wt / "docs" / "feature" / "001-todo-cli.md").read_text(encoding="utf-8")
        self.assertIn("**状態**: spec化済み（specs/001-todo-cli） |", text)
        self.assertIn("| MVP | spec化済み（specs/001-todo-cli） |", (wt / "docs" / "feature" / "README.md").read_text(encoding="utf-8"))
        self.checkpoints("1", "S3 S4 S5 S6 S7-1 S7-2 S7-3 S8 S9 S10 S11")
        self.assertIn("**状態**: 完了 |", (wt / "docs" / "feature" / "001-todo-cli.md").read_text(encoding="utf-8"))
        self.assertEqual(self.git("status", "--porcelain", cwd=wt), "")

    def test_resolve_rejects_ranges_and_taken_numbers(self) -> None:
        """M6: 範囲指定の文字列や、既存と番号が重なる完全名を新しいフィーチャーとして受け付けない。"""
        self.assertIn("範囲指定", self.out("resolve", "002-005"))
        self.assertIn("すでに 001-todo-cli", self.out("resolve", "001-todo-cl"))
        self.assertEqual(self.out("resolve", "003-new-thing"), "003-new-thing")

    def test_missing_main_branch(self) -> None:
        """M7: 既定のブランチがなければ、黙って空を返さずにエラーにする。SPECKIT_MAIN_BRANCH で変えられる。"""
        self.git("branch", "-m", "main", "master")
        proc = self.run_helper("next", "--phase", "spec")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("SPECKIT_MAIN_BRANCH", proc.stderr)
        env = {**self.env, "SPECKIT_MAIN_BRANCH": "master"}
        proc = subprocess.run([sys.executable, str(HELPER), "next", "--phase", "spec"], cwd=self.repo, env=env,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.stdout.strip(), "001-todo-cli")

    def test_next_skip(self) -> None:
        """M10: --skip で指定したフィーチャーを飛ばせる（途中の worktree も含む）。"""
        self.out("ensure", "1", "--phase", "spec")
        self.assertEqual(self.out("next", "--phase", "spec"), "001-todo-cli")
        self.assertEqual(self.out("next", "--phase", "spec", "--skip", "1"), "002-sync")
        self.assertEqual(self.out("next", "--phase", "spec", "--skip=001-todo-cli,002-sync"), "")

    def test_separate_git_dir(self) -> None:
        """M11: .git がファイルのリポジトリ（--separate-git-dir や submodule）でも動く。"""
        repo2 = self.tmp / "sep"
        subprocess.run(["git", "init", "-q", "-b", "main", "--separate-git-dir", str(self.tmp / "sep.git"), str(repo2)],
                       check=True, env=self.env)
        (repo2 / ".gitignore").write_text(".worktrees/\n", encoding="utf-8")
        self.git("add", "-A", cwd=repo2)
        self.git("commit", "-qm", "init", cwd=repo2)
        proc = self.run_helper("ensure", "001-x", "--phase", "spec", cwd=repo2)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"REPO_ROOT: {repo2}", proc.stdout)
        self.assertTrue((repo2 / ".worktrees" / "001-x").is_dir())

    def test_finish_guards(self) -> None:
        """L11・M5・L12: ステップの抜け、どのステップにも含まれない変更を止め、消える無視対象のファイルを知らせる。"""
        self.out("ensure", "1", "--phase", "spec")
        wt = self.repo / ".worktrees" / "001-todo-cli"
        self.spec_files(wt, "001-todo-cli")
        self.checkpoints("1", "S2 S4 S5 S6 S7-1 S7-2 S7-3")  # S3 が抜けている
        self.assertIn("未完了: S3", self.out("finish", "1", "--phase", "spec"))
        self.checkpoints("1", "S3")
        (wt / "debug.log.txt").write_text("x", encoding="utf-8")
        self.assertIn("LEFTOVER_CHANGES", self.out("finish", "1", "--phase", "spec"))
        self.assertEqual(self.git("status", "--porcelain", cwd=wt), "?? debug.log.txt")  # 止まった後もステージしない
        (wt / "debug.log.txt").unlink()
        (wt / ".worktrees-ignored").mkdir()
        (self.repo / ".gitignore").write_text(".worktrees/\n.env\n", encoding="utf-8")
        self.git("commit", "-qam", "ignore .env")
        self.git("merge", "-q", "main", cwd=wt)
        (wt / ".env").write_text("SECRET=1", encoding="utf-8")
        out = self.out("finish", "1", "--phase", "spec")
        self.assertIn("FINISHED: 001-todo-cli (spec)", out)
        self.assertIn("REMOVED_IGNORED: .env", out)

    def test_status_spec_done_unmerged(self) -> None:
        """L7: 仕様工程を終えて未マージの worktree は「完了（未マージ）」と表示する。"""
        self.out("ensure", "1", "--phase", "all")
        wt = self.repo / ".worktrees" / "001-todo-cli"
        self.spec_files(wt, "001-todo-cli")
        self.checkpoints("1", "S2 S3 S4 S5 S6 S7-1 S7-2 S7-3")
        self.assertIn("| 001-todo-cli | 完了（未マージ） | 未着手 |", self.out("status"))

    def test_human_tasks_merge_and_sync_status(self) -> None:
        """[人] のタスクだけが残っていれば止めずにマージし、状態は 人の作業待ち。片付けた後に sync-status で 完了 にする。"""
        fdir = self.repo / "docs" / "feature"
        (fdir / "001-todo-cli.md").write_text(
            "# TODO\n\n**状態**: 未着手 | **区分**: MVP | **想定順序**: 1 | **依存**: —\n", encoding="utf-8")
        (fdir / "README.md").write_text(
            "| # | 機能 | 区分 | 状態 | 依存 | 一言 |\n|---|---|---|---|---|---|\n"
            "| 1 | [TODO](./001-todo-cli.md) | MVP | 未着手 | — | a |\n", encoding="utf-8")
        (fdir / "spec_order.md").write_text("- **1. [TODO](./001-todo-cli.md)**: a\n", encoding="utf-8")
        self.git("add", "-A")
        self.git("commit", "-qm", "feature files")
        self.out("ensure", "1", "--phase", "all")
        wt = self.repo / ".worktrees" / "001-todo-cli"
        human = "- [ ] T002 [US1] [人] ドメインを取得する（完了の確かめ方: T003 が通る）"
        self.spec_files(wt, "001-todo-cli", tasks=f"- [x] T001\n{human}\n- [ ] T003 [US1] 設定を確かめる\n")
        self.checkpoints("1", "S2 S3 S4 S5 S6 S7-1 S7-2 S7-3 S8 S9 S10 S11")
        self.assertIn("| 残り 1 件 |", self.out("status"))
        self.assertIn("T002 [US1] [人]", self.out("human-tasks", "1"))
        status = "人の作業待ち（specs/001-todo-cli）"
        self.assertIn(f"**状態**: {status} |", (wt / "docs" / "feature" / "001-todo-cli.md").read_text(encoding="utf-8"))
        # AI のタスクが残っていれば止まり、[人] のタスクは一覧に含めない
        out = self.out("finish", "1", "--phase", "all")
        self.assertIn("UNCHECKED_TASKS", out)
        self.assertIn("T003", out)
        self.assertNotIn("T002", out)
        tasks = wt / "specs" / "001-todo-cli" / "tasks.md"
        tasks.write_text(f"- [x] T001\n{human}\n- [x] T003 [US1] 設定を確かめる\n", encoding="utf-8")
        self.checkpoints("1", "S11")
        # [人] のタスクだけなら、--allow-unchecked なしでマージして残りを知らせる
        out = self.out("finish", "1", "--phase", "all")
        self.assertIn("FINISHED: 001-todo-cli (all)", out)
        self.assertIn("HUMAN_TASKS_PENDING: 1", out)
        self.assertIn("T002", out)
        self.assertIn("| 001-todo-cli | 完了 | 完了 | - | 残り 1 件 |", self.out("status"))
        # 片付ける前の sync-status は 人の作業待ち のまま
        out = self.out("sync-status", "1")
        self.assertIn(f"FEATURE_STATUS: {status}", out)
        self.assertEqual(self.git("status", "--porcelain"), "")
        # 人のタスクを片付けて sync-status すると 完了 になる（コミットはしない）
        main_tasks = self.repo / "specs" / "001-todo-cli" / "tasks.md"
        main_tasks.write_text(main_tasks.read_text(encoding="utf-8").replace("- [ ] T002", "- [x] T002"),
                              encoding="utf-8")
        out = self.out("sync-status", "1")
        self.assertIn("FEATURE_STATUS: 完了", out)
        self.assertNotIn("HUMAN_TASKS_PENDING", out)
        self.assertIn("**状態**: 完了 |", (fdir / "001-todo-cli.md").read_text(encoding="utf-8"))
        self.assertIn("| MVP | 完了 |", (fdir / "README.md").read_text(encoding="utf-8"))
        self.assertIn("docs/feature/001-todo-cli.md", self.git("status", "--porcelain"))
        self.assertEqual(self.out("human-tasks"), "")

    def test_sync_status_guards(self) -> None:
        """sync-status は、実装までマージ済みのフィーチャーに main でだけ使える。"""
        self.assertIn("マージされていません", self.out("sync-status", "1"))
        self.out("ensure", "1", "--phase", "all")
        self.assertIn("worktree があります", self.out("sync-status", "1"))

    def test_gitignore_required(self) -> None:
        (self.repo / ".gitignore").write_text("", encoding="utf-8")
        self.git("commit", "-qam", "drop ignore")
        proc = self.run_helper("ensure", "1", "--phase", "spec")
        self.assertEqual(proc.returncode, 1)
        self.assertIn(".worktrees/", proc.stderr)

    # --- クラウドセッション ------------------------------------------------
    def finish_one(self, env: dict[str, str]) -> subprocess.CompletedProcess:
        """1 番目のフィーチャーを最後のステップまで進め、指定の環境で finish する。"""
        self.out("ensure", "1", "--phase", "all")
        wt = self.repo / ".worktrees" / "001-todo-cli"
        self.spec_files(wt, "001-todo-cli", tasks="- [x] T001\n")
        self.checkpoints("1", "S2 S3 S4 S5 S6 S7-1 S7-2 S7-3 S8 S9 S10 S11")
        return subprocess.run([sys.executable, str(HELPER), "finish", "1", "--phase", "all"], cwd=self.repo,
                              env=env, capture_output=True, text=True, encoding="utf-8")

    def test_local_merges_into_main_even_on_other_branch(self) -> None:
        """ローカル（CLAUDE_CODE_REMOTE なし）では従来どおり main がマージ先で、push もしない。"""
        self.git("switch", "-q", "-c", "claude/work")
        proc = self.finish_one(self.env)
        self.assertEqual(proc.returncode, 3, proc.stderr)
        self.assertIn("PRECONDITION: NOT_ON_MAIN", proc.stderr)
        self.assertIn("マージ先は main", proc.stderr)
        self.git("switch", "-q", "main")
        proc = self.run_helper("finish", "1", "--phase", "all")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("PUSH", proc.stdout)
        self.assertIn("merge(001-todo-cli): all", self.git("log", "-1", "--format=%s", "main"))

    def test_cloud_session_merges_into_working_branch_and_pushes(self) -> None:
        """クラウドセッションでは、今のブランチ（セッションの作業ブランチ）にマージし、origin に push する。"""
        remote = self.tmp / "remote.git"
        self.git("init", "-q", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("switch", "-q", "-c", "claude/work")
        cloud = {**self.env, "CLAUDE_CODE_REMOTE": "true"}
        proc = subprocess.run([sys.executable, str(HELPER), "ensure", "1", "--phase", "all"], cwd=self.repo,
                              env=cloud, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        wt = self.repo / ".worktrees" / "001-todo-cli"
        self.spec_files(wt, "001-todo-cli", tasks="- [x] T001\n")
        for step in "S2 S3 S4 S5 S6 S7-1 S7-2 S7-3 S8 S9 S10 S11".split():
            subprocess.run([sys.executable, str(HELPER), "checkpoint", "1", step, f"x: {step}"], cwd=self.repo,
                           env=cloud, check=True, capture_output=True)
        proc = subprocess.run([sys.executable, str(HELPER), "finish", "1", "--phase", "all"], cwd=self.repo,
                              env=cloud, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PUSHED: origin/claude/work", proc.stdout)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD"), "claude/work")
        self.assertIn("merge(001-todo-cli): all", self.git("log", "-1", "--format=%s", "claude/work"))
        self.assertNotIn("merge(", self.git("log", "--format=%s", "main"))
        self.assertEqual(self.git("rev-parse", "claude/work"),
                         self.git("--git-dir", str(remote), "rev-parse", "claude/work"))

    def test_cloud_session_respects_explicit_main_branch(self) -> None:
        """クラウドセッションでも、SPECKIT_MAIN_BRANCH を指定すればそちらを使う。push できなくてもマージは済ませる。"""
        cloud = {**self.env, "CLAUDE_CODE_REMOTE": "true", "SPECKIT_MAIN_BRANCH": "main"}
        proc = self.finish_one(cloud)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("PUSH_SKIPPED", proc.stdout)  # origin がない
        self.assertIn("merge(001-todo-cli): all", self.git("log", "-1", "--format=%s", "main"))

    def test_cloud_session_detached_head_falls_back_to_main(self) -> None:
        """作業ブランチを判定できない（detached HEAD）ときは main に戻す。"""
        self.git("checkout", "-q", "--detach")
        cloud = {**self.env, "CLAUDE_CODE_REMOTE": "true"}
        proc = subprocess.run([sys.executable, str(HELPER), "next", "--phase", "spec"], cwd=self.repo, env=cloud,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.stdout.strip(), "001-todo-cli", proc.stderr)


if __name__ == "__main__":
    unittest.main()

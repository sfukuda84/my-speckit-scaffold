"""new-speckit-project のテスト。作業ツリーの scaffold を一時的な Git リポジトリにして、そこから作成する。"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCAFFOLD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCAFFOLD / "tool" / "src"))

from new_speckit_project import cli  # noqa: E402

GIT_ENV = {
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


class NewProjectTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.env_backup = dict(os.environ)
        os.environ.update(GIT_ENV)
        os.environ["GIT_CONFIG_GLOBAL"] = str(Path(tempfile.mkdtemp()) / "gitconfig")
        Path(os.environ["GIT_CONFIG_GLOBAL"]).write_text("[user]\n\tname = t\n\temail = t@example.com\n",
                                                        encoding="utf-8")
        # 作業ツリーの scaffold（未コミットの変更を含む）を、一時的なリポジトリとして用意する
        cls.tmp = Path(tempfile.mkdtemp()).resolve()
        cls.repo = cls.tmp / "scaffold"
        shutil.copytree(SCAFFOLD, cls.repo, symlinks=True,
                        ignore=shutil.ignore_patterns(".git", ".worktrees", "__pycache__"))
        git("init", "-q", "-b", "main", cwd=cls.repo)
        git("add", "-A", cwd=cls.repo)
        git("commit", "-qm", "scaffold", cwd=cls.repo)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.tmp, ignore_errors=True)
        os.environ.clear()
        os.environ.update(cls.env_backup)

    def create(self, name: str, *extra: str) -> tuple[int, Path]:
        target = self.tmp / name
        args = cli.build_parser().parse_args(
            [str(target), "--repo", str(self.repo), "--no-launch", *extra])
        return cli.create_project(args), target

    def test_create_project(self) -> None:
        code, target = self.create("my-app", "-m", "小規模な整骨院の予約と施術記録を一つにまとめる。")
        self.assertEqual(code, 0)
        # scaffold 固有のものは持ち込まない
        self.assertFalse((target / "tool").exists())
        self.assertTrue((target / "docs" / "speckit-scaffold.md").is_file())
        self.assertIn("# my-app", (target / "README.md").read_text(encoding="utf-8"))
        # スキルのリンクは相対パスで、共有スキルを指す
        for rel in cli.SKILL_DIRS:
            link = target / rel / "speckit-bootstrap"
            self.assertTrue(link.is_symlink(), link)
            self.assertEqual(os.readlink(link), os.path.join("..", "..", "skills", "speckit", "speckit-bootstrap"))
            self.assertTrue((link / "SKILL.md").is_file())
        concept = (target / cli.CONCEPT_FILE).read_text(encoding="utf-8")
        self.assertIn("整骨院", concept)
        self.assertFalse((target / "docs" / "concept" / ".gitkeep").exists())
        # 履歴は新しく 1 コミットだけ、main でクリーン
        self.assertEqual(git("rev-list", "--count", "HEAD", cwd=target), "1")
        self.assertEqual(git("branch", "--show-current", cwd=target), "main")
        self.assertEqual(git("status", "--porcelain", cwd=target), "")
        self.assertIn("Scaffold:", git("log", "-1", "--format=%B", cwd=target))
        # 作成したプロジェクトで worktree 管理のスクリプトが動く
        helper = target / ".claude" / "skills" / "speckit-worktree" / "scripts" / "worktree_helper.py"
        proc = subprocess.run([sys.executable, str(helper), "status"], cwd=target,
                              capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_rejects_non_empty_target(self) -> None:
        target = self.tmp / "occupied"
        target.mkdir()
        (target / "x.txt").write_text("x", encoding="utf-8")
        args = cli.build_parser().parse_args([str(target), "--repo", str(self.repo), "--no-launch", "-m", "x"])
        with self.assertRaises(cli.CliError):
            cli.create_project(args)

    def test_cleans_up_when_clone_fails(self) -> None:
        target = self.tmp / "bad-ref"
        args = cli.build_parser().parse_args(
            [str(target), "--repo", str(self.repo), "--ref", "no-such-branch", "--no-launch", "-m", "x"])
        with self.assertRaises(cli.CliError):
            cli.create_project(args)
        self.assertFalse(target.exists())

    def test_symlink_fallback_to_copy(self) -> None:
        code, target = self.create("win-like", "-m", "テスト")
        self.assertEqual(code, 0)
        # Windows でリンクを作れない場合の再現: git がリンク先のパスを書いた通常のファイルとして取り出した状態
        link = target / ".kiro" / "skills" / "speckit-plan"
        link.unlink()
        link.write_text("../../skills/speckit/speckit-plan", encoding="utf-8")

        def failing_symlink(*_args, **_kwargs):
            raise OSError("symlink not permitted")

        copied = cli.ensure_skill_links(target, symlink=failing_symlink)
        self.assertEqual(copied, [".kiro/skills/speckit-plan"])
        self.assertTrue(link.is_dir() and not link.is_symlink())
        self.assertTrue((link / "SKILL.md").is_file())

    def test_symlink_recreated_from_plain_file(self) -> None:
        code, target = self.create("relink", "-m", "テスト")
        self.assertEqual(code, 0)
        link = target / ".claude" / "skills" / "speckit-tasks"
        link.unlink()
        link.write_text("../../skills/speckit/speckit-tasks", encoding="utf-8")
        self.assertEqual(cli.ensure_skill_links(target), [])
        self.assertTrue(link.is_symlink() and (link / "SKILL.md").is_file())


class ReadConceptTest(unittest.TestCase):
    def test_message(self) -> None:
        self.assertEqual(cli.read_concept("  概要  ", None), "概要")

    def test_interactive_stops_at_two_blank_lines(self) -> None:
        stdin = io.StringIO("1 行目\n\n2 行目\n\n\n無視される\n")
        self.assertEqual(cli.read_concept(None, None, stdin=stdin, interactive=True), "1 行目\n\n2 行目")

    def test_piped_stdin(self) -> None:
        self.assertEqual(cli.read_concept(None, None, stdin=io.StringIO("パイプ入力\n"), interactive=False),
                         "パイプ入力")

    def test_empty_is_error(self) -> None:
        with self.assertRaises(cli.CliError):
            cli.read_concept(None, None, stdin=io.StringIO("\n\n"), interactive=True)


class AgentCommandTest(unittest.TestCase):
    def which(self, name: str) -> str:
        return f"/bin/{name}"

    def test_commands(self) -> None:
        root = Path("/tmp/proj")
        self.assertEqual(cli.agent_command("claude", root, self.which), ["/bin/claude", "/speckit-bootstrap"])
        self.assertEqual(cli.agent_command("agy", root, self.which),
                         ["/bin/agy", "--prompt-interactive", "/speckit-bootstrap"])
        self.assertEqual(cli.agent_command("kiro", root, self.which)[:2], ["/bin/kiro-cli", "chat"])
        self.assertEqual(cli.agent_command("opencode", root, self.which)[:2], ["/bin/opencode", "--prompt"])
        codex = cli.agent_command("codex", root, self.which)
        self.assertEqual(codex[-1], "$speckit-bootstrap")
        self.assertIn("workspace-write", codex)
        self.assertTrue(any(a.startswith("sandbox_workspace_write.writable_roots=['") and a.endswith(".git']")
                            for a in codex))

    def test_missing_cli(self) -> None:
        self.assertIsNone(cli.agent_command("claude", Path("."), lambda _n: None))

    def test_detect_python(self) -> None:
        self.assertEqual(cli.detect_python(lambda n: "/x" if n == "python" else None), "python")
        self.assertIsNone(cli.detect_python(lambda _n: None))


if __name__ == "__main__":
    unittest.main()

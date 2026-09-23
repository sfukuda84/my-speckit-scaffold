"""new-speckit-project update のテスト。一時的な scaffold からプロジェクトを作り、scaffold を更新して取り込む。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCAFFOLD = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCAFFOLD / "tool" / "src"))

from new_speckit_project import cli, update  # noqa: E402


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout.strip()


class UpdateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.env_backup = dict(os.environ)
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        gitconfig = self.tmp / "gitconfig"
        gitconfig.write_text("[user]\n\tname = t\n\temail = t@example.com\n", encoding="utf-8")
        os.environ["GIT_CONFIG_GLOBAL"] = str(gitconfig)
        # scaffold の v1（作業ツリーの内容）
        self.repo = self.tmp / "scaffold"
        shutil.copytree(SCAFFOLD, self.repo, symlinks=True,
                        ignore=shutil.ignore_patterns(".git", ".worktrees", "__pycache__"))
        git("init", "-q", "-b", "main", cwd=self.repo)
        git("add", "-A", cwd=self.repo)
        git("commit", "-qm", "v1", cwd=self.repo)
        self.url = self.repo.as_uri()
        # v1 からプロジェクトを作る
        self.project = self.tmp / "app"
        args = cli.build_parser().parse_args([str(self.project), "--repo", self.url, "--no-launch", "-m", "テスト"])
        self.assertEqual(cli.create_project(args), 0)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)
        os.environ.clear()
        os.environ.update(self.env_backup)

    def run_update(self, *extra: str) -> int:
        return cli.main(["update", str(self.project), "--repo", self.url, *extra])

    def release_v2(self) -> None:
        """scaffold の v2: スキルの修正・追加・ファイルの削除・ルールの変更・.gitignore の追加。"""
        r = self.repo
        plan = r / "skills" / "speckit" / "speckit-plan" / "SKILL.md"
        plan.write_text(plan.read_text(encoding="utf-8") + "\n<!-- v2 -->\n", encoding="utf-8")
        new_skill = r / "skills" / "speckit" / "speckit-newskill"
        new_skill.mkdir()
        (new_skill / "SKILL.md").write_text("---\nname: speckit-newskill\n---\n", encoding="utf-8")
        for d in cli.SKILL_DIRS:
            os.symlink("../../skills/speckit/speckit-newskill", r / d / "speckit-newskill", target_is_directory=True)
        (r / ".specify" / "integrations" / "speckit.manifest.json").unlink()
        lang = r / ".kiro" / "steering" / "language.md"
        lang.write_text(lang.read_text(encoding="utf-8") + "\n- v2 の追記\n", encoding="utf-8")
        with open(r / ".gitignore", "a", encoding="utf-8") as handle:
            handle.write("\n*.v2cache\n")
        git("add", "-A", cwd=r)
        git("commit", "-qm", "v2", cwd=r)

    def test_update_applies_changes_and_keeps_local_edits(self) -> None:
        p = self.project
        # プロジェクトで手で直したファイル（scaffold のどの版とも一致しない）
        lang = p / ".kiro" / "steering" / "language.md"
        lang.write_text(lang.read_text(encoding="utf-8") + "\n- プロジェクト独自のルール\n", encoding="utf-8")
        # プロジェクト独自のスキル（scaffold に一度も現れていない）
        own = p / "skills" / "speckit" / "speckit-own"
        own.mkdir()
        (own / "SKILL.md").write_text("own\n", encoding="utf-8")
        git("add", "-A", cwd=p)
        git("commit", "-qm", "local edits", cwd=p)
        self.release_v2()
        before = git("rev-parse", "HEAD", cwd=p)

        self.assertEqual(self.run_update("--dry-run"), 0)
        self.assertEqual(git("rev-parse", "HEAD", cwd=p), before)  # --dry-run では何も変えない
        self.assertEqual(git("status", "--porcelain", cwd=p), "")

        self.assertEqual(self.run_update(), 0)
        # スキルの修正と追加（リンクも張られる）
        self.assertIn("<!-- v2 -->", (p / "skills/speckit/speckit-plan/SKILL.md").read_text(encoding="utf-8"))
        for d in cli.SKILL_DIRS:
            link = p / d / "speckit-newskill"
            self.assertTrue(link.is_symlink() and (link / "SKILL.md").is_file(), link)
        # scaffold から消えた（手で直していない）ファイルは削除
        self.assertFalse((p / ".specify/integrations/speckit.manifest.json").exists())
        # 手で直したファイルは触らず、新しい版を .scaffold-new/ に置く
        self.assertIn("プロジェクト独自のルール", lang.read_text(encoding="utf-8"))
        self.assertNotIn("v2 の追記", lang.read_text(encoding="utf-8"))
        self.assertIn("v2 の追記", (p / ".scaffold-new/.kiro/steering/language.md").read_text(encoding="utf-8"))
        # プロジェクト独自のスキルは残る
        self.assertTrue((own / "SKILL.md").is_file())
        # .gitignore に足りない行を足す（.scaffold-new/ も）
        gi = (p / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("*.v2cache", gi)
        self.assertIn(".scaffold-new/", gi)
        # 1 つのコミットにまとまり、元にした版が記録される
        self.assertEqual(git("status", "--porcelain", cwd=p), "")
        self.assertIn("Scaffold:", git("log", "-1", "--format=%B", cwd=p))
        sha = git("rev-parse", "HEAD", cwd=self.repo)
        self.assertIn(sha, (p / cli.STATE_FILE).read_text(encoding="utf-8"))
        self.assertIn(sha[:7], (p / cli.SCAFFOLD_README).read_text(encoding="utf-8"))

        # 2 回目は何も変わらない
        head = git("rev-parse", "HEAD", cwd=p)
        self.assertEqual(self.run_update(), 0)
        self.assertEqual(git("rev-parse", "HEAD", cwd=p), head)

    def test_refuses_dirty_or_non_scaffold_project(self) -> None:
        (self.project / "memo.txt").write_text("x", encoding="utf-8")
        self.assertEqual(self.run_update(), 1)
        other = self.tmp / "other"
        other.mkdir()
        git("init", "-q", "-b", "main", cwd=other)
        self.assertEqual(cli.main(["update", str(other), "--repo", self.url]), 1)

    def test_is_managed(self) -> None:
        self.assertTrue(update.is_managed("skills/speckit/speckit-plan/SKILL.md"))
        self.assertTrue(update.is_managed(".claude/skills/speckit-plan"))
        self.assertTrue(update.is_managed(".kiro/steering/language.md"))
        for path in ("docs/feature/001-a.md", "specs/001-a/spec.md", ".specify/memory/constitution.md",
                     "README.md", "tool/pyproject.toml", "src/app.py"):
            self.assertFalse(update.is_managed(path), path)


if __name__ == "__main__":
    unittest.main()

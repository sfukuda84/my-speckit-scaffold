"""new-speckit-project update: 作成済みのプロジェクトに、scaffold の新しい版（スキル、スクリプト、ルールなど）を取り込む。

判定の考え方:
  scaffold の持ち物（MANAGED_PREFIXES / MANAGED_FILES）の各ファイルについて、scaffold の全履歴に現れた版の
  ハッシュを集める。プロジェクト側のファイルがそのどれかと一致すれば「手で直していない」とみなして、
  新しい版で上書きする（scaffold から消えたファイルは削除する）。一致しなければ手で直したものとして触らず、
  scaffold の新しい版を .scaffold-new/ に置いて報告する。プロジェクトの成果物（docs/concept、docs/feature、
  specs、憲章、ソースコード、README.md など）は対象外。
"""

from __future__ import annotations

import filecmp
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import cli

MANAGED_PREFIXES = (
    "skills/speckit/",
    ".claude/skills/speckit-",
    ".agents/skills/speckit-",
    ".kiro/skills/speckit-",
    ".specify/scripts/",
    ".specify/templates/",
    ".specify/workflows/",
    ".specify/integrations/",
    ".opencode/commands/speckit.",
    ".kiro/steering/",
)
MANAGED_FILES = (
    "CLAUDE.md", "AGENTS.md", "GEMINI.md", "opencode.json", "MANUAL.md", "THIRD_PARTY_NOTICES.md",
    ".specify/init-options.json", ".specify/integration.json", ".specify/.gitignore",
)
NEW_VERSIONS_DIR = ".scaffold-new"


def is_managed(path: str) -> bool:
    if any(path == rel or path.startswith(rel + "/") for rel in cli.EXCLUDED_PATHS):
        return False
    return path in MANAGED_FILES or path.startswith(MANAGED_PREFIXES)


@dataclass
class Plan:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)      # 手で直されているので触らないもの
    kept_removed: list[str] = field(default_factory=list)  # scaffold から消えたが手で直されているので残すもの
    mirrors: list[str] = field(default_factory=list)       # コピーで置かれたスキル（Windows）を作り直すもの
    gitignore_lines: list[str] = field(default_factory=list)
    scaffold_doc: bool = False

    def changes(self) -> int:
        return (len(self.added) + len(self.updated) + len(self.deleted) + len(self.mirrors)
                + len(self.gitignore_lines) + int(self.scaffold_doc))


def git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise cli.CliError(f"git {' '.join(args)} が失敗しました。\n{proc.stderr.strip()}")
    return proc.stdout


def tree_entries(repo: Path, rev: str) -> dict[str, tuple[str, str]]:
    """path -> (mode, blob)。"""
    entries = {}
    for record in git(["ls-tree", "-r", "-z", rev], repo).split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        mode, kind, blob = meta.split()
        if kind == "blob":
            entries[path] = (mode, blob)
    return entries


def known_versions(repo: Path) -> dict[str, set[str]]:
    """scaffold の全履歴で、各パスに現れた版のハッシュ。"""
    known: dict[str, set[str]] = {}
    for rev in git(["rev-list", "HEAD"], repo).split():
        for path, (_mode, blob) in tree_entries(repo, rev).items():
            if is_managed(path):
                known.setdefault(path, set()).add(blob)
    return known


def project_entries(project: Path) -> dict[str, tuple[str, str]]:
    """プロジェクトで Git が追跡しているファイルの path -> (mode, blob)（作業ツリーはクリーンである前提）。"""
    entries = {}
    for record in git(["ls-files", "-s", "-z"], project).split("\0"):
        if not record:
            continue
        meta, path = record.split("\t", 1)
        mode, blob, _stage = meta.split()
        entries[path] = (mode, blob)
    return entries


def copied_skill_dirs(project: Path) -> list[tuple[str, str]]:
    """シンボリックリンクではなく実体のコピーで置かれたスキル（Windows の代わりの方法）の (リンクの位置, スキル名)。"""
    result = []
    for rel_dir in cli.SKILL_DIRS:
        base = project / rel_dir
        if base.is_dir():
            for entry in sorted(base.iterdir()):
                if entry.name.startswith("speckit-") and entry.is_dir() and not entry.is_symlink():
                    result.append((f"{rel_dir}/{entry.name}", entry.name))
    return result


def same_tree(a: Path, b: Path) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _match, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    if mismatch or errors:
        return False
    return all(same_tree(a / d, b / d) for d in cmp.common_dirs)


def build_plan(project: Path, scaffold: Path, repo: str, ref: str, sha: str) -> tuple[Plan, dict[str, tuple[str, str]]]:
    new = {p: e for p, e in tree_entries(scaffold, "HEAD").items() if is_managed(p)}
    known = known_versions(scaffold)
    have = {p: e for p, e in project_entries(project).items() if is_managed(p)}
    copies = copied_skill_dirs(project)
    copy_roots = tuple(root + "/" for root, _ in copies)
    plan = Plan()

    for path, (_mode, blob) in sorted(new.items()):
        if path.startswith(copy_roots) or any(path == root for root, _ in copies):
            continue  # コピーで置かれたスキルは下でまとめて扱う
        if path not in have:
            plan.added.append(path)
        elif have[path][1] == blob:
            continue
        elif have[path][1] in known.get(path, set()):
            plan.updated.append(path)
        else:
            plan.modified.append(path)
    for path, (_mode, blob) in sorted(have.items()):
        if path in new or path.startswith(copy_roots):
            continue
        if blob in known.get(path, set()):
            plan.deleted.append(path)
        elif path in known:
            plan.kept_removed.append(path)
        # scaffold に一度も現れていないファイルは、プロジェクト独自のものなので触らない

    for root, name in copies:
        source = project / "skills" / "speckit" / name
        if source.is_dir() and same_tree(project / root, source):
            plan.mirrors.append(root)
        else:
            plan.modified.append(root + "/")

    current = set((project / ".gitignore").read_text(encoding="utf-8").splitlines()) \
        if (project / ".gitignore").is_file() else set()
    wanted = (scaffold / ".gitignore").read_text(encoding="utf-8").splitlines() \
        if (scaffold / ".gitignore").is_file() else []
    wanted.append(f"{NEW_VERSIONS_DIR}/")
    plan.gitignore_lines = [line for line in wanted if line.strip() and not line.startswith("#") and line not in current]

    readme = scaffold / "README.md"
    doc = project / cli.SCAFFOLD_README
    if readme.is_file():
        expected = cli.scaffold_doc_text(readme.read_text(encoding="utf-8"), repo, ref, sha)
        plan.scaffold_doc = not doc.is_file() or doc.read_text(encoding="utf-8") != expected
    return plan, new


def write_blob(scaffold: Path, project: Path, path: str, mode: str, blob: str) -> None:
    target = project / path
    if target.is_symlink() or target.is_file():
        target.unlink()
    elif target.is_dir():
        cli.remove_tree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if mode == "120000":
        # Git はリンク先を / 区切りで記録する。Windows のディレクトリへのリンクは / 区切りだとたどれないので、OS の区切りに直す
        link = git(["cat-file", "-p", blob], scaffold).strip().replace("/", os.sep)
        try:
            os.symlink(link, target, target_is_directory=True)
            if not target.exists():  # 作れてもたどれないリンクは使わない
                target.unlink()
                raise OSError(f"{target} のリンク先をたどれない")
        except (OSError, NotImplementedError):
            shutil.copytree((target.parent / link).resolve(), target)
    else:
        shutil.copy2(scaffold / path, target)


def apply_plan(plan: Plan, project: Path, scaffold: Path, new: dict[str, tuple[str, str]],
               repo: str, ref: str, sha: str) -> None:
    # 実体（skills/speckit/）を先に更新し、リンクやコピーはその後に作る
    order = sorted(plan.added + plan.updated, key=lambda p: (not p.startswith("skills/"), p))
    for path in order:
        mode, blob = new[path]
        write_blob(scaffold, project, path, mode, blob)
    for path in plan.deleted:
        target = project / path
        if target.is_symlink() or target.is_file():
            target.unlink()
        parent = target.parent
        while parent != project and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    for root in plan.mirrors:
        cli.remove_tree(project / root)
    # 足りないリンク（新しいスキル、コピーを作り直すもの）を作る
    for rel_dir in cli.SKILL_DIRS:
        for skill in sorted((project / "skills" / "speckit").iterdir()):
            link = project / rel_dir / skill.name
            if skill.is_dir() and not link.exists() and not link.is_symlink():
                link.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.symlink(os.path.relpath(skill, link.parent), link, target_is_directory=True)
                except (OSError, NotImplementedError):
                    shutil.copytree(skill, link)
    # 手で直されたファイルは触らず、scaffold の新しい版を .scaffold-new/ に置く
    for path in plan.modified:
        path = path.rstrip("/")
        if path in new:
            dest = project / NEW_VERSIONS_DIR / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            mode, blob = new[path]
            if mode == "120000":
                dest.write_text(git(["cat-file", "-p", blob], scaffold), encoding="utf-8")
            else:
                shutil.copy2(scaffold / path, dest)
    if plan.gitignore_lines:
        gi = project / ".gitignore"
        text = gi.read_text(encoding="utf-8") if gi.is_file() else ""
        if text and not text.endswith("\n"):
            text += "\n"
        text += "\n# ===== my-speckit-scaffold の更新で追加 =====\n" + "\n".join(plan.gitignore_lines) + "\n"
        gi.write_text(text, encoding="utf-8")
    if plan.scaffold_doc:
        cli.write_scaffold_doc(project, (scaffold / "README.md").read_text(encoding="utf-8"), repo, ref, sha)


def check_project(project: Path) -> None:
    if not (project / "skills" / "speckit").is_dir():
        raise cli.CliError(f"{project} は my-speckit-scaffold から作ったプロジェクトではないようです（skills/speckit/ がない）。")
    top = Path(git(["rev-parse", "--show-toplevel"], project).strip()).resolve()
    if top != project:
        raise cli.CliError(f"プロジェクトのルート（{top}）を指定してください。")
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"], project).strip()
    main = os.environ.get("SPECKIT_MAIN_BRANCH", "main")
    if branch != main:
        raise cli.CliError(f"{main} ブランチで実行してください（現在: {branch}）。")
    if git(["status", "--porcelain"], project).strip():
        raise cli.CliError("未コミットの変更があります。コミットまたは stash してから実行してください。")


def print_plan(plan: Plan) -> None:
    def section(title: str, items: list[str]) -> None:
        if items:
            cli.info(f"{title}（{len(items)}）:")
            for item in items:
                cli.info(f"  {item}")

    section("追加", plan.added)
    section("更新", plan.updated)
    section("削除", plan.deleted)
    section("コピーを作り直すスキル", plan.mirrors)
    section(".gitignore に足す行", plan.gitignore_lines)
    if plan.scaffold_doc:
        cli.info(f"scaffold の README の写しを更新: {cli.SCAFFOLD_README}")
    section(f"手で直されているので触らない（新しい版は {NEW_VERSIONS_DIR}/ に置く）", plan.modified)
    section("scaffold から消えたが、手で直されているので残す", plan.kept_removed)


def run_update(args) -> int:
    project = Path(args.project).expanduser().resolve()
    check_project(project)
    worktrees = [line[len("worktree "):] for line in git(["worktree", "list", "--porcelain"], project).splitlines()
                 if line.startswith("worktree ")][1:]
    with tempfile.TemporaryDirectory() as tmp:
        scaffold = Path(tmp) / "scaffold"
        cli.info(f"==> scaffold を取得します: {args.repo}（{args.ref}）")
        git(["clone", "--quiet", "--branch", args.ref, args.repo, str(scaffold)], Path(tmp))
        sha = git(["rev-parse", "HEAD"], scaffold).strip()
        plan, new = build_plan(project, scaffold, args.repo, args.ref, sha)
        print_plan(plan)
        if args.dry_run:
            cli.info("確認のみ行いました（--dry-run）。")
            return 0
        apply_plan(plan, project, scaffold, new, args.repo, args.ref, sha)
        cli.write_state(project, args.repo, args.ref, sha)
    git(["add", "-A"], project)
    if git(["status", "--porcelain"], project).strip():
        git(["commit", "--quiet", "-m", f"chore: my-speckit-scaffold を更新（{sha[:7]}）",
             "-m", f"Scaffold: {args.repo} {args.ref} ({sha})"], project)
        cli.info(f"==> 更新をコミットしました: {git(['rev-parse', '--short', 'HEAD'], project).strip()}")
    else:
        cli.info("==> すでに最新です。")
    if plan.modified:
        cli.info(f"==> 手で直されたファイルが {len(plan.modified)} 件あります。scaffold の新しい版と比べて、必要なら取り込んでください:")
        cli.info(f"      git diff --no-index <ファイル> {NEW_VERSIONS_DIR}/<ファイル>")
    if worktrees:
        cli.info("==> 作業中の worktree があります。worktree の中のスキルは、main にマージするまで更新前のままです:")
        for wt in worktrees:
            cli.info(f"      {wt}")
    return 0

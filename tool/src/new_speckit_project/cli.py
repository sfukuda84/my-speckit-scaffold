"""new-speckit-project: my-speckit-scaffold から新規プロジェクトを作成し、AI エージェントで立ち上げを始める。

手順:
  C1 scaffold を GitHub から clone し、tool/ と scaffold の履歴を取り除く
  C2 スキルのシンボリックリンクを確かめる（作れない環境では実体のコピーに切り替える）
  C3 コアコンセプトを docs/concept/core-concept.md に保存し、git init と初回コミットを行う
  C4 指定のエージェントを対話モードで起動し、speckit-bootstrap を渡す

macOS / Linux / Windows で動くように、標準ライブラリだけで書く（Python 3.9 以上）。
"""

from __future__ import annotations

import argparse
import datetime
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Callable

from . import __version__

DEFAULT_REPO = "https://github.com/sfukuda84/my-speckit-scaffold.git"
DEFAULT_REF = "main"
SKILL_DIRS = (".claude/skills", ".agents/skills", ".kiro/skills")
SHARED_SKILLS = "skills/speckit"
# 新規プロジェクトに持ち込まない scaffold 側のファイル（scaffold 自体の開発用）
EXCLUDED_PATHS = ("tool", ".github/workflows/scaffold-tests.yml")
SCAFFOLD_README = "docs/speckit-scaffold.md"
CONCEPT_FILE = "docs/concept/core-concept.md"


class CliError(Exception):
    """利用者に伝えて終了するエラー。"""


# --- エージェントの起動方法 ---------------------------------------------------

def _codex_command(exe: str, root: Path) -> list[str]:
    # workspace-write のサンドボックスでは .git が読み取り専用になり、コミットやブランチの作成ができない。
    # サンドボックスは保ったまま、.git だけを書き込み可能にする（TOML のリテラル文字列で Windows のパスも扱う）。
    # 立ち上げのスキルは出典付きの Web 調査を行い、実装では依存パッケージを取得するので、Web 検索とネットワークも有効にする。
    git_dir = str((root / ".git").resolve())
    return [exe, "--sandbox", "workspace-write", "--search",
            "-c", f"sandbox_workspace_write.writable_roots=['{git_dir}']",
            "-c", "sandbox_workspace_write.network_access=true",
            "$speckit-bootstrap"]


NATURAL_PROMPT = "speckit-bootstrap スキルを使って、このプロジェクトの立ち上げを進めてください。"

AGENTS: dict[str, tuple[str, Callable[[str, Path], list[str]]]] = {
    "claude": ("claude", lambda exe, root: [exe, "/speckit-bootstrap"]),
    "codex": ("codex", _codex_command),
    "agy": ("agy", lambda exe, root: [exe, "--prompt-interactive", "/speckit-bootstrap"]),
    "kiro": ("kiro-cli", lambda exe, root: [exe, "chat", NATURAL_PROMPT]),
    "opencode": ("opencode", lambda exe, root: [exe, "--prompt", NATURAL_PROMPT]),
}

MANUAL_INVOCATION = {
    "claude": "claude を起動して /speckit-bootstrap",
    "codex": "codex を起動して $speckit-bootstrap（.git への書き込み、Web 検索、ネットワークを許可すること）",
    "agy": "agy を起動して /speckit-bootstrap",
    "kiro": f"kiro-cli chat を起動して「{NATURAL_PROMPT}」",
    "opencode": f"opencode を起動して「{NATURAL_PROMPT}」",
}


def agent_command(agent: str, root: Path, which: Callable[[str], str | None] = shutil.which) -> list[str] | None:
    """エージェントの起動コマンド。CLI が見つからなければ None。"""
    name, build = AGENTS[agent]
    exe = which(name)
    return build(exe, root) if exe else None


# --- 小さな道具 -----------------------------------------------------------------

def info(message: str) -> None:
    print(message, file=sys.stderr)


def run_git(args: list[str], cwd: Path | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise CliError(f"git {' '.join(args)} が失敗しました。\n{proc.stderr.strip()}")
    return proc.stdout.strip()


def remove_tree(path: Path) -> None:
    """Windows の読み取り専用ファイル（.git/objects など）も消せるように削除する。"""

    def on_error(func, target, _exc_info):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path, onerror=on_error)


def clear_directory(path: Path) -> None:
    """ディレクトリ自体は残して、中身だけを消す（元から空だったディレクトリに作成して失敗した場合の片付け）。"""
    for child in path.iterdir():
        remove_tree(child)


def _runs_python3(exe: str) -> bool:
    """本当に Python 3.9 以上が動くか（Windows の Microsoft Store の代わりの実行ファイルを除くため、実際に起動する）。"""
    code = "import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)"
    args = [exe, "-3", "-c", code] if Path(exe).stem.lower() == "py" else [exe, "-c", code]
    try:
        return subprocess.run(args, capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def detect_python(which: Callable[[str], str | None] = shutil.which,
                  runs: Callable[[str], bool] = _runs_python3) -> str | None:
    """スキルのスクリプトを動かせる Python のコマンド名。"""
    for name in ("python3", "python", "py"):
        exe = which(name)
        if exe and runs(exe):
            return "py -3" if name == "py" else name
    return None


# --- C0: 事前確認とコンセプトの受け取り -------------------------------------------

def check_target(target: Path) -> None:
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise CliError(f"{target} はすでに存在し、空ではありません。新しいディレクトリを指定してください。")


def check_git_identity() -> None:
    """新しいリポジトリでコミットできるか。今いるディレクトリのリポジトリの設定に左右されないよう、一時ディレクトリで確かめる。"""
    if shutil.which("git") is None:
        raise CliError("git が見つかりません。Git をインストールしてください。")
    proc = subprocess.run(["git", "var", "GIT_COMMITTER_IDENT"], cwd=tempfile.gettempdir(),
                          capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise CliError("git の user.name と user.email が設定されていません。"
                       "`git config --global user.name <名前>` と `git config --global user.email <アドレス>` で設定してください。")


def read_text_any(path: Path) -> str:
    """UTF-8（BOM 付きも可）で読み、読めなければ Windows の日本語の既定（cp932）で読む。"""
    try:
        data = path.read_bytes()
    except OSError as error:
        raise CliError(f"{path} を読めません: {error}") from error
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise CliError(f"{path} の文字コードを判定できません。UTF-8 で保存してください。")


def read_concept(message: str | None, concept_file: str | None,
                 stdin=None, interactive: bool | None = None) -> str:
    """コアコンセプトの本文。-m、--concept-file、対話入力（または標準入力）の順に使う。"""
    stdin = stdin or sys.stdin
    if message is not None:
        text = message
    elif concept_file is not None:
        text = read_text_any(Path(concept_file))
    else:
        if interactive is None:
            interactive = stdin.isatty()
        if interactive:
            print("サービスのコアコンセプトを入力してください（誰の、どんな課題を、どう解決するか）。", file=sys.stderr)
            print("空行を 2 回続けるか、Ctrl-D（Windows は Ctrl-Z → Enter）で入力を終えます。", file=sys.stderr)
            lines: list[str] = []
            blank = 0
            for line in stdin:
                line = line.rstrip("\r\n")
                blank = blank + 1 if not line.strip() else 0
                if blank >= 2:
                    break
                lines.append(line)
            text = "\n".join(lines)
        else:
            text = stdin.read()
    text = text.strip()
    if not text:
        raise CliError("コアコンセプトが空です。-m で指定するか、対話入力で入力してください。")
    return text


# --- C1: clone と scaffold 固有ファイルの除去 --------------------------------------

def clone_scaffold(repo: str, ref: str, target: Path) -> str:
    """scaffold を clone し、元のコミットの SHA を返す。"""
    info(f"==> scaffold を取得します: {repo}（{ref}）")
    # core.symlinks は強制しない。Windows でシンボリックリンクを作れない環境で true を強制すると clone 自体が失敗するため、
    # git の既定の判定に任せ、リンクが通常のファイルとして取り出された場合は ensure_skill_links で直す。
    run_git(["clone", "--quiet", "--depth", "1", "--branch", ref, repo, str(target)])
    return run_git(["rev-parse", "HEAD"], cwd=target)


def strip_scaffold(target: Path) -> None:
    remove_tree(target / ".git")
    for rel in EXCLUDED_PATHS:
        path = target / rel
        remove_tree(path)
        # 除いた結果、空になった親ディレクトリ（.github/workflows など）も消す
        parent = path.parent
        while parent != target and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


# --- C2: シンボリックリンクの確認 -------------------------------------------------

def ensure_skill_links(root: Path, symlink: Callable[..., None] = os.symlink) -> list[str]:
    """各エージェントのスキルディレクトリが共有スキルを指すようにする。コピーに切り替えたものの一覧を返す。

    Windows でシンボリックリンクを作れない環境では、git はリンクをリンク先のパスを書いた通常のファイルとして
    取り出す。その場合はリンクを作り直し、それもできなければスキルの実体をコピーする。
    """
    shared = root / SHARED_SKILLS
    copied: list[str] = []
    for rel_dir in SKILL_DIRS:
        skill_dir = root / rel_dir
        if not skill_dir.is_dir():
            continue
        for entry in sorted(skill_dir.iterdir()):
            if entry.is_symlink() and entry.exists():
                continue
            if entry.is_dir() and not entry.is_symlink():
                continue  # すでに実体（コピー済みなど）
            name = entry.name
            source = shared / name
            if not source.is_dir():
                raise CliError(f"{entry} のリンク先 {source} がありません。scaffold が壊れている可能性があります。")
            relative = os.path.relpath(source, skill_dir)
            entry.unlink()
            try:
                symlink(relative, entry, target_is_directory=True)
            except (OSError, NotImplementedError):
                shutil.copytree(source, entry)
                copied.append(f"{rel_dir}/{name}")
    return copied


# --- C3: README、コンセプト、初回コミット -------------------------------------------

def write_project_files(root: Path, concept: str, repo: str, ref: str, sha: str) -> None:
    readme = root / "README.md"
    if readme.exists():
        moved = root / SCAFFOLD_README
        moved.parent.mkdir(parents=True, exist_ok=True)
        original = readme.read_text(encoding="utf-8")
        web = repo.removesuffix(".git")
        # scaffold の README の写し。tool/ は持ち込まないので、tool/README.md への相対リンクは GitHub の URL に直す
        if web.startswith("https://"):
            original = original.replace("](tool/README.md)", f"]({web}/blob/{ref}/tool/README.md)")
        moved.write_text(
            f"> この文書は、プロジェクトの作成に使った scaffold（{web}、{ref}、{sha[:7]}）の README の写しである。"
            "scaffold 自体の開発に関する節（「scaffold の更新」など）は、このプロジェクトには当てはまらない。\n\n"
            + original, encoding="utf-8")
        readme.unlink()
    name = root.name
    readme.write_text(
        f"# {name}\n\n"
        f"このプロジェクトは [my-speckit-scaffold]({repo.removesuffix('.git')})"
        f"（{ref}、{sha[:7]}）から作成した。\n"
        "Spec Kit による仕様駆動開発の進め方は "
        f"[{SCAFFOLD_README}]({SCAFFOLD_README}) を参照する。\n\n"
        "## 立ち上げ\n\n"
        "エージェントで `speckit-bootstrap` スキルを実行し、コアコンセプトから機能一覧、アーキテクチャ、憲章、"
        "共通基盤、非機能要件までを作る。その後は `speckit-all` で 1 件ずつ仕様化と実装を進める。\n",
        encoding="utf-8",
    )
    concept_path = root / CONCEPT_FILE
    concept_path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.date.today().isoformat()
    concept_path.write_text(f"# コアコンセプト\n\n**作成日**: {today}\n\n{concept}\n", encoding="utf-8")
    gitkeep = concept_path.parent / ".gitkeep"
    if gitkeep.exists():
        gitkeep.unlink()


def init_repository(root: Path, repo: str, ref: str, sha: str) -> None:
    try:
        run_git(["init", "--quiet", "-b", "main"], cwd=root)
    except CliError:
        # git 2.28 より前は -b がない
        run_git(["init", "--quiet"], cwd=root)
        run_git(["symbolic-ref", "HEAD", "refs/heads/main"], cwd=root)
    run_git(["add", "-A"], cwd=root)
    run_git(["commit", "--quiet", "-m", "chore: my-speckit-scaffold から初期化",
             "-m", f"Scaffold: {repo} {ref} ({sha})"], cwd=root)


# --- C4: エージェントの起動 -------------------------------------------------------

def launch_agent(agent: str, root: Path, no_launch: bool) -> int:
    command = None if no_launch else agent_command(agent, root)
    if command is None:
        if not no_launch:
            info(f"警告: {AGENTS[agent][0]} が見つからないため、エージェントを起動しませんでした。")
        info("次の手順で立ち上げを始めてください:")
        info(f"  cd {root}")
        info(f"  {MANUAL_INVOCATION[agent]}")
        return 0
    info(f"==> {AGENTS[agent][0]} を起動し、speckit-bootstrap を始めます。")
    return subprocess.call(command, cwd=str(root))


# --- 本体 -----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="new-speckit-project",
        description="my-speckit-scaffold から新規プロジェクトを作成し、AI エージェントで立ち上げ（speckit-bootstrap）を始める。",
    )
    parser.add_argument("target", help="作成するプロジェクトのディレクトリ（存在しないか、空であること）")
    concept = parser.add_mutually_exclusive_group()
    concept.add_argument("-m", "--message", help="サービスのコアコンセプト。省略時は対話で入力を受ける")
    concept.add_argument("--concept-file", help="コアコンセプトを書いたファイル（UTF-8）")
    parser.add_argument("--agent", choices=sorted(AGENTS), default="claude",
                        help="立ち上げに使うエージェント（既定: claude）")
    parser.add_argument("--ref", default=os.environ.get("SPECKIT_SCAFFOLD_REF", DEFAULT_REF),
                        help=f"scaffold のブランチまたはタグ（既定: {DEFAULT_REF}）")
    parser.add_argument("--repo", default=os.environ.get("SPECKIT_SCAFFOLD_REPO", DEFAULT_REPO),
                        help="scaffold の Git リポジトリ（既定: my-speckit-scaffold の GitHub）")
    parser.add_argument("--no-launch", action="store_true", help="エージェントを起動せず、手順の案内だけを表示する")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def create_project(args: argparse.Namespace, stdin=None) -> int:
    target = Path(args.target).expanduser().resolve()
    check_target(target)
    check_git_identity()
    concept = read_concept(args.message, args.concept_file, stdin=stdin)

    created = not target.exists()
    try:
        sha = clone_scaffold(args.repo, args.ref, target)
        strip_scaffold(target)
        copied = ensure_skill_links(target)
        write_project_files(target, concept, args.repo, args.ref, sha)
        init_repository(target, args.repo, args.ref, sha)
    except BaseException:
        if created and target.exists():
            remove_tree(target)
        elif target.exists():
            clear_directory(target)  # 元から空だったディレクトリは残し、中身だけを消す
        raise

    info(f"==> プロジェクトを作成しました: {target}")
    if copied:
        info(f"警告: シンボリックリンクを作れなかったため、{len(copied)} 個のスキルを実体のコピーにしました。")
        info("      スキルを更新するときは skills/speckit/ を直したうえで、各エージェントのスキルディレクトリにも反映してください。")
        info("      Windows では開発者モードを有効にすると、シンボリックリンクを使えるようになります。")
    python = detect_python()
    if python is None:
        info("警告: Python が見つかりません。Spec Kit とスキルのスクリプトには Python 3.9 以上が必要です。")
    elif python != "python3":
        info(f"注意: python3 が使えないため、スキルのスクリプトは {python} で実行されます（steering に読み替えのルールがあります）。")
    return launch_agent(args.agent, target, args.no_launch)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return create_project(args)
    except CliError as error:
        print(f"エラー: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n中断しました。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())

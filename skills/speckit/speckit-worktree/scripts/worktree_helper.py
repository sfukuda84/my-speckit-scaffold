#!/usr/bin/env python3
"""worktree_helper.py - speckit-feature / speckit-coding / speckit-all 共通の worktree 管理

各フィーチャーを .worktrees/<FEATURE_NAME>（ブランチ feature/<FEATURE_NAME>）で作業し、
ステップ完了ごとのコミットに付けた trailer "Speckit-Step: <STEP>" と "Speckit-Feature: <FEATURE_NAME>" で
進捗を判定する。フィーチャー名付きの trailer は main にマージされた後も残るので、マージ後も進捗を失わない。
プロジェクトのルートから実行しても worktree の中から実行しても同じように動く。
macOS / Linux / Windows で動くように、標準ライブラリだけで書く（Python 3.9 以上）。
"""

from __future__ import annotations

import functools
import os
import re
import subprocess
import sys
from pathlib import Path

# マージ先のブランチ。main() で resolve_main_branch() の結果に置き換える（ローカルでは従来どおり main）。
MAIN_BRANCH = os.environ.get("SPECKIT_MAIN_BRANCH") or "main"
# Claude Code のクラウドセッション（VM 内では CLAUDE_CODE_REMOTE=true）。push できるのはセッションの作業ブランチだけで、
# VM は回収されると消えるため、マージ先を作業ブランチにし、マージ後に push する。
CLOUD_SESSION = os.environ.get("CLAUDE_CODE_REMOTE") == "true"
SPEC_STEPS = ["S2", "S3", "S4", "S5", "S6", "S7-1", "S7-2", "S7-3"]
CODING_STEPS = ["S8", "S9", "S10", "S11"]
ALL_STEPS = SPEC_STEPS + CODING_STEPS
PHASE_STEPS = {"spec": SPEC_STEPS, "coding": CODING_STEPS, "all": ALL_STEPS}
PHASE_LAST_STEP = {"spec": "S7-3", "coding": "S11", "all": "S11"}
# feature.json はローカル状態なので、.gitignore の設定にかかわらずコミットしない。
FEATURE_JSON = ".specify/feature.json"
ORDER_LINE_RE = re.compile(r"\*\*\s*([0-9]+)\.\s*\[[^\]]*\]\(\./([^.)]+)\.md\)")
TRAILER_RE = re.compile(r"^Speckit-Step:\s*(\S+)", re.MULTILINE)
FEATURE_TRAILER_RE = re.compile(r"^Speckit-Feature:\s*(\S+)", re.MULTILINE)
MERGE_SUBJECT_RE = re.compile(r"^merge\(([^)]+)\): (spec|coding|all)$", re.MULTILINE)
UNCHECKED_RE = re.compile(r"^[ \t]*- \[ \].*$", re.MULTILINE)
# 人が行うタスクの印（steering の「人が行うタスク」）。未完了でも AI の実装漏れとして扱わない。
HUMAN_MARKER = "[人]"
COMMIT_SEP = "\x1e"
# 機能ファイルの状態欄（speckit-concept-2-feature の様式）
STATUS_SPECIFIED = "spec化済み（specs/{name}）"
STATUS_DONE = "完了"
STATUS_HUMAN_PENDING = "人の作業待ち（specs/{name}）"
NEW_FEATURE_RE = re.compile(r"^[0-9]{3}-[a-z0-9][a-z0-9-]*$")

REPO_ROOT: Path = Path()
WORKTREES_DIR: Path = Path()


class HelperError(Exception):
    """終了コード 1 で終わるエラー。"""


class Precondition(Exception):
    """前提条件を満たさないときの停止。スキル側で案内を出すため終了コード 3 で終わる。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def info(message: str) -> None:
    print(message, file=sys.stderr)


def run_git(args: list[str], cwd: Path | None = None, check: bool = True,
            quiet: bool = False) -> subprocess.CompletedProcess:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and proc.returncode != 0:
        if not quiet:
            sys.stderr.write(proc.stdout)
            sys.stderr.write(proc.stderr)
        raise HelperError(f"git {' '.join(args)} が失敗しました（終了コード {proc.returncode}）。")
    return proc


def git_out(args: list[str], cwd: Path | None = None) -> str:
    return run_git(args, cwd=cwd).stdout.strip()


def git_ok(args: list[str], cwd: Path | None = None) -> bool:
    return run_git(args, cwd=cwd, check=False).returncode == 0


def git_passthrough(args: list[str], cwd: Path | None = None) -> None:
    """git の出力を stderr に流しながら実行する（進行状況の表示用）。"""
    proc = run_git(args, cwd=cwd, check=False)
    sys.stderr.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    if proc.returncode != 0:
        raise HelperError(f"git {' '.join(args)} が失敗しました（終了コード {proc.returncode}）。")


def find_repo_root() -> Path:
    """worktree の中から実行しても、メインの作業ツリーのルートを返す。

    - メインの作業ツリーの中なら、その最上位（--show-toplevel）。.git がファイルになっている
      submodule や --separate-git-dir のリポジトリでも正しく求められる。
    - このスクリプトが作った worktree（<ルート>/.worktrees/<名前>）の中なら、その 2 つ上。
    - それ以外の worktree の中なら、git worktree list の先頭。
    """
    def rev_parse(*args: str) -> str:
        proc = subprocess.run(["git", "rev-parse", *args], capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            raise HelperError("Git リポジトリの中で実行してください。")
        return proc.stdout.strip()

    toplevel = Path(rev_parse("--show-toplevel")).resolve()
    git_dir = Path(rev_parse("--absolute-git-dir")).resolve()
    common = Path(rev_parse("--git-common-dir"))
    common = (common if common.is_absolute() else Path.cwd() / common).resolve()
    if git_dir == common:
        return toplevel
    if toplevel.parent.name == ".worktrees":
        return toplevel.parent.parent
    proc = subprocess.run(["git", "worktree", "list", "--porcelain"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    for line in proc.stdout.splitlines():
        if line.startswith("worktree "):
            return Path(line[len("worktree "):]).resolve()
    raise HelperError("メインの作業ツリーを特定できません。")


def resolve_main_branch() -> str:
    """マージ先のブランチ。SPECKIT_MAIN_BRANCH、クラウドセッションの作業ブランチ、main の順に決める。

    クラウドセッションでは、メインの作業ツリーが今いるブランチ（セッションの作業ブランチ）をマージ先にする。
    detached HEAD やフィーチャーのブランチにいるときは作業ブランチを判定できないので、main に戻す。
    """
    explicit = os.environ.get("SPECKIT_MAIN_BRANCH")
    if explicit:
        return explicit
    if CLOUD_SESSION:
        current = run_git(["rev-parse", "--abbrev-ref", "HEAD"], check=False).stdout.strip()
        if current and current != "HEAD" and not current.startswith("feature/"):
            return current
    return "main"


def push_after_merge() -> None:
    """クラウドセッションで、マージ先のブランチを origin に push する（VM が回収されてもマージの結果を残すため）。"""
    if not CLOUD_SESSION:
        return
    if not git_ok(["remote", "get-url", "origin"]):
        print("PUSH_SKIPPED: origin がありません")
        return
    proc = run_git(["push", "-u", "origin", MAIN_BRANCH], check=False)
    if proc.returncode == 0:
        print(f"PUSHED: origin/{MAIN_BRANCH}")
    else:
        # クラウドセッションでは作業ブランチ以外への push は拒否される。マージ自体は済んでいるので止めない。
        info(proc.stderr.strip())
        print(f"PUSH_FAILED: origin/{MAIN_BRANCH}（クラウドセッションで push できるのは作業ブランチだけ）")


def branch_of(name: str) -> str:
    return f"feature/{name}"


def worktree_of(name: str) -> Path:
    return WORKTREES_DIR / name


def branch_exists(name: str) -> bool:
    return git_ok(["rev-parse", "--verify", "-q", f"refs/heads/{branch_of(name)}"])


def main_has_file(name: str, filename: str) -> bool:
    return git_ok(["cat-file", "-e", f"{MAIN_BRANCH}:specs/{name}/{filename}"])


def main_has_tasks(name: str) -> bool:
    return main_has_file(name, "tasks.md")


def main_has_all_artifacts(name: str) -> bool:
    return all(main_has_file(name, f) for f in ("spec.md", "plan.md", "tasks.md"))


@functools.lru_cache(maxsize=None)
def history(ref: str) -> tuple[dict[str, frozenset], frozenset]:
    """ref から辿れる全コミットを読み、(フィーチャーごとの完了ステップ, 実装までマージ済みのフィーチャー) を返す。"""
    proc = run_git(["log", ref, f"--format=%B{COMMIT_SEP}"], check=False)
    steps: dict[str, set[str]] = {}
    merged: set[str] = set()
    if proc.returncode == 0:
        for body in proc.stdout.split(COMMIT_SEP):
            feature = FEATURE_TRAILER_RE.search(body)
            if feature:
                steps.setdefault(feature.group(1), set()).update(TRAILER_RE.findall(body))
            for name, phase in MERGE_SUBJECT_RE.findall(body):
                if phase in ("coding", "all"):
                    merged.add(name)
    return {k: frozenset(v) for k, v in steps.items()}, frozenset(merged)


def forget_history() -> None:
    """コミットやマージで履歴が変わった後に呼ぶ。"""
    history.cache_clear()


def coding_done(name: str) -> bool:
    """実装工程まで main にマージ済みか（main 上の S11 の記録か、merge(<name>): coding|all のコミットで判定する）。"""
    steps, merged = history(MAIN_BRANCH)
    return "S11" in steps.get(name, frozenset()) or name in merged


def split_unchecked(text: str) -> tuple[list[str], list[str]]:
    """未完了のタスク行を (AI のタスク, 人のタスク) に分けて返す。"""
    ai: list[str] = []
    human: list[str] = []
    for line in UNCHECKED_RE.findall(text):
        (human if HUMAN_MARKER in line else ai).append(line.strip())
    return ai, human


def unchecked_tasks(tasks_file: Path) -> tuple[list[str], list[str]]:
    if not tasks_file.is_file():
        return [], []
    return split_unchecked(tasks_file.read_text(encoding="utf-8"))


def main_tasks_text(name: str) -> str:
    proc = run_git(["show", f"{MAIN_BRANCH}:specs/{name}/tasks.md"], check=False)
    return proc.stdout if proc.returncode == 0 else ""


def status_after_coding(name: str, tasks_file: Path) -> str:
    """実装を終えた後の状態。人のタスクが残っていれば 人の作業待ち、なければ 完了。"""
    _, human = unchecked_tasks(tasks_file)
    return STATUS_HUMAN_PENDING.format(name=name) if human else STATUS_DONE


def completed_steps(name: str) -> list[str]:
    """完了済みのステップ。

    - main とブランチの全履歴にある、このフィーチャー名付きの trailer
    - ブランチ上の main にないコミットの trailer（フィーチャー名がない旧形式も含む）
    - 仕様が main にマージ済み（tasks.md がある）なら S2〜S7-3
    - 実装まで main にマージ済みなら全ステップ
    """
    found: set[str] = set(history(MAIN_BRANCH)[0].get(name, frozenset()))
    if branch_exists(name):
        found.update(history(branch_of(name))[0].get(name, frozenset()))
        log = git_out(["log", f"{MAIN_BRANCH}..{branch_of(name)}", "--format=%B"])
        found.update(TRAILER_RE.findall(log))
    if main_has_tasks(name):
        found.update(SPEC_STEPS)
    if coding_done(name):
        found.update(ALL_STEPS)
    return [step for step in ALL_STEPS if step in found]


def next_step(name: str, phase: str) -> str:
    done = set(completed_steps(name))
    for step in PHASE_STEPS[phase]:
        if step not in done:
            return step
    return "S12"


def read_spec_order() -> str:
    proc = run_git(["show", f"{MAIN_BRANCH}:docs/feature/spec_order.md"], check=False)
    if proc.returncode == 0:
        return proc.stdout
    path = REPO_ROOT / "docs" / "feature" / "spec_order.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return ""


def get_all_features() -> list[str]:
    """フィーチャー名を着手順に並べて返す。

    docs/feature/spec_order.md（任意）にあるものはその並び順（着手順の正本）で先に置き、
    そこにない main の specs/ と .worktrees/ のものは番号順で後ろに足す。
    """
    ordered: list[str] = []
    for match in ORDER_LINE_RE.finditer(read_spec_order()):
        num, slug = match.group(1), match.group(2)
        # 新形式はファイル名が NNN-slug で、そのまま specs/ の名前になる。旧形式は slug だけなので番号を付ける。
        name = slug if re.match(r"^[0-9]{3}-", slug) else f"{int(num):03d}-{slug}"
        if name not in ordered:
            ordered.append(name)
    rest: set[str] = set()
    proc = run_git(["ls-tree", "-d", "--name-only", MAIN_BRANCH, "specs/"], check=False)
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            if line.startswith("specs/"):
                rest.add(line[len("specs/"):])
    if WORKTREES_DIR.is_dir():
        for child in WORKTREES_DIR.iterdir():
            if child.is_dir():
                rest.add(child.name)
    return ordered + sorted(n for n in rest if n and n not in ordered)


def resolve_feature(query: str | None) -> str:
    """短い番号（1, 002）、スラッグ、完全名（001-todo-cli）、ファイルパスからフィーチャー名を決める。"""
    if not query:
        raise HelperError("フィーチャーを指定してください。")
    query = Path(query.replace("\\", "/")).name
    if query.endswith(".md"):
        query = query[:-3]
    padded = f"{int(query):03d}" if query.isdigit() else query

    matches: list[str] = []
    for feat in get_all_features():
        if feat == query:
            return feat
        if feat.startswith(f"{padded}-") or feat.endswith(f"-{query}"):
            matches.append(feat)
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise HelperError(f"'{query}' に一致するフィーチャーが複数あります: {' '.join(matches)}")
    # 一覧にない新しいフィーチャーは、完全名（NNN-slug）で指定されたときだけ受け付ける。
    if NEW_FEATURE_RE.match(query):
        number, slug = query.split("-", 1)
        if re.fullmatch(r"[0-9-]+", slug):
            raise HelperError(
                f"'{query}' は範囲指定に見えます。範囲は list の結果から 1 件ずつ選び、完全名か番号で指定してください。")
        taken = [f for f in get_all_features() if f.startswith(f"{number}-")]
        if taken:
            raise HelperError(
                f"番号 {number} はすでに {' '.join(taken)} が使っています。綴りを確かめるか、別の番号にしてください。")
        return query
    raise HelperError(
        f"'{query}' に一致するフィーチャーが見つかりません（docs/feature/spec_order.md、specs/、.worktrees/ を検索）。"
        "新しいフィーチャーは 001-short-name の形の完全名で指定してください。"
    )


def stage_all(worktree: Path) -> None:
    run_git(["add", "-A"], cwd=worktree)
    run_git(["reset", "-q", "--", FEATURE_JSON], cwd=worktree, check=False)


def worktree_branch(worktree: Path) -> str | None:
    proc = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else None


def update_feature_status(wt: Path, name: str, status: str, only_from: tuple[str, ...] = ()) -> list[str]:
    """docs/feature/ の機能ファイルの状態欄と、README.md の一覧の状態列を status にする。更新したファイルを返す。

    only_from を指定したときは、今の状態がそのいずれかの場合だけ更新する（状態を後戻りさせないため）。
    機能ファイルがないプロジェクトでは何もしない。
    """
    feature_dir = wt / "docs" / "feature"
    slug = name.split("-", 1)[1] if re.match(r"^[0-9]{3}-", name) else name
    target = next((p for p in (feature_dir / f"{name}.md", feature_dir / f"{slug}.md") if p.is_file()), None)
    if target is None:
        return []
    changed: list[str] = []
    text = target.read_text(encoding="utf-8")
    m = re.search(r"(\*\*状態\*\*:\s*)([^|\n]+?)(\s*\|)", text)
    if m is None:
        return []
    current = m.group(2).strip()
    if current == status or (only_from and not any(current.startswith(p) for p in only_from)):
        return []
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text[:m.start(2)] + status + text[m.end(2):])
    changed.append(str(target.relative_to(wt)))
    readme = feature_dir / "README.md"
    if readme.is_file():
        lines = readme.read_text(encoding="utf-8").split("\n")
        row_re = re.compile(r"^\|\s*\d+\s*\|\s*\[[^\]]*\]\(\./" + re.escape(target.stem) + r"\.md\)\s*\|")
        updated = False
        for i, line in enumerate(lines):
            if row_re.match(line):
                cells = line.split("|")
                # ['', ' # ', ' 機能 ', ' 区分 ', ' 状態 ', ' 依存 ', ' 一言 ', '']
                if len(cells) > 5:
                    cells[4] = f" {status} "
                    lines[i] = "|".join(cells)
                    updated = True
        if updated:
            with open(readme, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(lines))
            changed.append(str(readme.relative_to(wt)))
    return changed


def print_state(name: str, phase: str, wt_state: str) -> None:
    print(f"REPO_ROOT: {REPO_ROOT}")
    print(f"FEATURE_NAME: {name}")
    print(f"BRANCH: {branch_of(name)}")
    print(f"WORKTREE_DIR: {worktree_of(name)}")
    print(f"WORKTREE_STATE: {wt_state}")
    print(f"PHASE: {phase}")
    print(f"COMPLETED_STEPS: {' '.join(completed_steps(name))}")
    print(f"NEXT_STEP: {next_step(name, phase)}")


def parse_args(args: list[str]) -> tuple[str | None, str | None, list[str]]:
    """(最初の位置引数, --phase の値, その他のフラグ) を返す。"""
    positional: str | None = None
    phase: str | None = None
    flags: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--phase":
            phase = args[i + 1] if i + 1 < len(args) else ""
            i += 2
            continue
        if arg == "--skip":  # 値を取るフラグ。値は cmd_next が読む
            i += 2
            continue
        if arg.startswith("--phase="):
            phase = arg[len("--phase="):]
        elif arg.startswith("--"):
            flags.append(arg)
        elif positional is None:
            positional = arg
        i += 1
    return positional, phase, flags


def require_phase(phase: str | None) -> str:
    if not phase:
        raise HelperError("--phase spec|coding|all を指定してください。")
    if phase not in PHASE_STEPS:
        raise HelperError(f"--phase には spec / coding / all のいずれかを指定してください（指定値: '{phase}'）。")
    return phase


def check_phase_precondition(name: str, phase: str, wt: Path) -> None:
    done = completed_steps(name)
    if phase == "spec":
        if not wt.is_dir() and main_has_tasks(name):
            raise Precondition(
                "ALREADY_SPECIFIED",
                f"{name} の仕様（tasks.md）はすでに {MAIN_BRANCH} にマージされています。実装は speckit-coding で行ってください。",
            )
        if "S8" in done:
            raise Precondition(
                "CODING_IN_PROGRESS",
                f"{name} の worktree はすでに実装工程に入っています。speckit-coding または speckit-all で再開してください。",
            )
    elif phase == "coding":
        if "S7-3" not in done:
            if wt.is_dir() or branch_exists(name):
                raise Precondition(
                    "SPEC_INCOMPLETE",
                    f"{name} の仕様工程（S2〜S7-3）が終わっていません（次: {next_step(name, 'spec')}）。"
                    "speckit-feature または speckit-all で再開してください。",
                )
            raise Precondition(
                "SPEC_MISSING",
                f"{name} の spec.md / plan.md / tasks.md が {MAIN_BRANCH} にも worktree にもありません。"
                "先に speckit-feature または speckit-all を実行してください。",
            )
        if not wt.is_dir() and not main_has_all_artifacts(name):
            raise Precondition(
                "SPEC_MISSING",
                f"{name} の spec.md / plan.md / tasks.md が {MAIN_BRANCH} にそろっていません。"
                "先に speckit-feature または speckit-all を実行してください。",
            )
    if phase != "spec" and not wt.is_dir() and not branch_exists(name) and coding_done(name):
        raise Precondition("ALREADY_IMPLEMENTED", f"{name} は実装まで {MAIN_BRANCH} にマージ済みです。")


def repo_is_dirty() -> bool:
    return bool(git_out(["status", "--porcelain"]))


def cmd_ensure(args: list[str]) -> None:
    positional, phase, _ = parse_args(args)
    phase = require_phase(phase)
    name = resolve_feature(positional)
    branch = branch_of(name)
    wt = worktree_of(name)

    run_git(["worktree", "prune"])
    check_phase_precondition(name, phase, wt)

    if wt.is_dir():
        current = worktree_branch(wt)
        if current is None:
            raise HelperError(f"{wt} は Git の worktree ではありません。手動で確認してください。")
        if current != branch:
            raise HelperError(f"{wt} のブランチが '{current}' です（期待値: '{branch}'）。手動で確認してください。")
        wt_state = "reused"
    else:
        if not git_ok(["check-ignore", "-q", ".worktrees/"]):
            raise HelperError(
                ".worktrees/ が .gitignore に登録されていません。"
                ".gitignore に '.worktrees/' を追加してコミットしてから再実行してください。"
            )
        if repo_is_dirty():
            info(git_out(["status", "--short"]))
            raise HelperError(f"{REPO_ROOT} に未コミットの変更があります。コミットまたは stash してから再実行してください。")
        WORKTREES_DIR.mkdir(parents=True, exist_ok=True)
        if branch_exists(name):
            info(f"==> 既存のブランチ {branch} に worktree を作り直します: {wt}")
            git_passthrough(["worktree", "add", str(wt), branch])
            wt_state = "reattached"
        else:
            info(f"==> {MAIN_BRANCH} から {branch} と worktree を作成します: {wt}")
            git_passthrough(["worktree", "add", "-b", branch, str(wt), MAIN_BRANCH])
            wt_state = "created"

    # feature.json は speckit の各スキルが対象ディレクトリの特定に使う。
    (wt / ".specify").mkdir(parents=True, exist_ok=True)
    (wt / "specs" / name).mkdir(parents=True, exist_ok=True)
    # Windows でも LF で書く（Path.write_text の newline 引数は 3.10 以降のため open を使う）。
    with open(wt / FEATURE_JSON, "w", encoding="utf-8", newline="\n") as handle:
        handle.write('{\n  "feature_directory": "specs/%s"\n}\n' % name)
    print_state(name, phase, wt_state)


def cmd_state(args: list[str]) -> None:
    positional, phase, _ = parse_args(args)
    phase = require_phase(phase)
    name = resolve_feature(positional)
    print_state(name, phase, "present" if worktree_of(name).is_dir() else "absent")


def cmd_checkpoint(args: list[str]) -> None:
    if len(args) < 3:
        raise HelperError("使い方: checkpoint <feature> <step> <subject>")
    name = resolve_feature(args[0])
    step, subject = args[1], args[2]
    if step not in ALL_STEPS:
        raise HelperError(f"ステップ '{step}' は不正です（有効値: {' '.join(ALL_STEPS)}）。")
    wt = worktree_of(name)
    if not wt.is_dir():
        raise HelperError(f"worktree {wt} がありません。先に ensure を実行してください。")
    current = worktree_branch(wt)
    if current != branch_of(name):
        raise HelperError(f"{wt} のブランチが '{current}' です。")

    # 機能ファイルの状態欄を進める（仕様を作ったら spec化済み、実装を終えたら 完了。人のタスクが残れば 人の作業待ち）
    if step == "S2":
        for path in update_feature_status(wt, name, STATUS_SPECIFIED.format(name=name), only_from=("未着手",)):
            info(f"==> 状態を更新しました: {path}")
    elif step == "S11":
        status = status_after_coding(name, wt / "specs" / name / "tasks.md")
        for path in update_feature_status(wt, name, status):
            info(f"==> 状態を更新しました: {path}")

    stage_all(wt)
    run_git(["commit", "-q", "--allow-empty", "-m", subject,
             "-m", f"Speckit-Step: {step}\nSpeckit-Feature: {name}"], cwd=wt)
    forget_history()
    print(f"CHECKPOINT: {step} {git_out(['rev-parse', '--short', 'HEAD'], cwd=wt)}")
    print(f"NEXT_STEP: {next_step(name, 'all')}")


def cmd_finish(args: list[str]) -> None:
    positional, phase, flags = parse_args(args)
    phase = require_phase(phase)
    name = resolve_feature(positional)
    branch = branch_of(name)
    wt = worktree_of(name)
    last = PHASE_LAST_STEP[phase]

    if not wt.is_dir():
        raise HelperError(f"worktree {wt} がありません。")
    # worktree の中で実行すると、削除後にシェルが消えたディレクトリに残る（Windows では削除自体が失敗する）
    cwd = Path.cwd().resolve()
    if cwd == wt.resolve() or wt.resolve() in cwd.parents:
        raise HelperError(f"finish は worktree の外（{REPO_ROOT}）で実行してください。`cd {REPO_ROOT}` してから再実行します。")
    done = completed_steps(name)
    missing = [step for step in PHASE_STEPS[phase] if step not in done]
    if missing:
        raise HelperError(f"{phase} 工程のステップが完了していません（未完了: {' '.join(missing)}）。")
    for filename in ("spec.md", "plan.md", "tasks.md"):
        if not (wt / "specs" / name / filename).is_file():
            raise HelperError(f"{wt / 'specs' / name / filename} がありません。")
    human_pending: list[str] = []
    if phase in ("coding", "all"):
        remaining, human_pending = unchecked_tasks(wt / "specs" / name / "tasks.md")
        if remaining and "--allow-unchecked" not in flags:
            raise Precondition(
                "UNCHECKED_TASKS",
                f"{name} の tasks.md に未完了のタスク（{HUMAN_MARKER} 以外）が {len(remaining)} 件あります。"
                "一覧をユーザーに示し、残したままマージしてよいと確認できたら --allow-unchecked を付けて再実行してください。\n"
                + "\n".join(remaining),
            )

    stage_all(wt)
    if not git_ok(["diff", "--cached", "--quiet"], cwd=wt):
        if "--commit-leftovers" not in flags:
            files = git_out(["diff", "--cached", "--name-status"], cwd=wt)
            run_git(["reset", "-q"], cwd=wt)
            raise Precondition(
                "LEFTOVER_CHANGES",
                f"{wt} に、どのステップにも含まれていない変更があります。\n{files}\n"
                "内容をユーザーに示し、マージに含めてよいと確認できたら --commit-leftovers を付けて再実行してください。"
                "含めない変更は、ユーザーの了承を得て取り除いてから再実行してください。",
            )
        info("==> worktree の残りの変更をコミットします。")
        run_git(["commit", "-q", "-m", f"chore({name}): マージ前の残りの変更",
                 "-m", f"Speckit-Feature: {name}"], cwd=wt)

    # マージ後の片付けで止まらないよう、マージの前に worktree がクリーンであることを確かめる。
    leftover = git_out(["status", "--porcelain", "--", ".", f":(exclude){FEATURE_JSON}"], cwd=wt)
    if leftover:
        info(leftover)
        raise HelperError(f"{wt} にコミットできない変更が残っています。確認してから再実行してください。")
    if repo_is_dirty():
        info(git_out(["status", "--short"]))
        raise HelperError(f"{REPO_ROOT} に未コミットの変更があるためマージできません。コミットまたは stash してから再実行してください。")
    current = git_out(["rev-parse", "--abbrev-ref", "HEAD"])
    if current != MAIN_BRANCH:
        if "--switch" not in flags:
            raise Precondition(
                "NOT_ON_MAIN",
                f"{REPO_ROOT} のブランチが {current} です（マージ先は {MAIN_BRANCH}）。"
                f"{MAIN_BRANCH} に切り替えてよいかをユーザーに確認し、よければ --switch を付けて再実行してください。",
            )
        info(f"==> {REPO_ROOT} を {MAIN_BRANCH} に切り替えます（現在: {current}）。")
        run_git(["checkout", "-q", MAIN_BRANCH])

    if git_ok(["merge-base", "--is-ancestor", branch, MAIN_BRANCH]):
        # 競合を解消して手でマージした後の再実行など。ブランチはすでに main に入っているので片付けだけ行う。
        info(f"==> {branch} はすでに {MAIN_BRANCH} にマージ済みです。片付けだけを行います。")
    else:
        info(f"==> {branch} を {MAIN_BRANCH} に --no-ff でマージします。")
        try:
            git_passthrough(["merge", "--no-ff", "-m", f"merge({name}): {phase}", branch])
        except HelperError as error:
            raise HelperError(
                f"マージで競合しました。{REPO_ROOT} で競合を解消してマージをコミットし、"
                "もう一度 finish を実行してください（worktree とブランチは残しています）。"
            ) from error
    forget_history()

    info("==> worktree とブランチを削除します。")
    ignored = [line[3:] for line in git_out(["status", "--porcelain", "--ignored", "--untracked-files=normal"], cwd=wt)
               .splitlines() if line.startswith("!! ") and line[3:].rstrip("/") != FEATURE_JSON]
    if ignored:
        info("==> 次の無視対象のファイルは worktree と一緒に削除されます（.env など必要なものはメインの作業ツリーに控えてください）:")
        for path in ignored:
            info(f"      {path}")
    # 変更はすべてマージ済みで、残るのは無視対象のローカル状態だけなので --force で削除する。
    run_git(["worktree", "remove", "--force", str(wt)])
    git_passthrough(["branch", "-d", branch])
    print(f"FINISHED: {name} ({phase})")
    if ignored:
        print(f"REMOVED_IGNORED: {' '.join(ignored)}")
    print(f"MERGE_COMMIT: {git_out(['rev-parse', '--short', 'HEAD'])}")
    push_after_merge()
    if human_pending:
        # 人のタスクだけが残っているときは止めずにマージし、残りを知らせる。
        print(f"HUMAN_TASKS_PENDING: {len(human_pending)}")
        for line in human_pending:
            print(f"  {line}")


def cmd_abort(args: list[str]) -> None:
    positional, _, flags = parse_args(args)
    name = resolve_feature(positional)
    branch = branch_of(name)
    wt = worktree_of(name)
    print(f"対象: {name}")
    if wt.is_dir():
        print(f"  削除する worktree: {wt}（未コミットの変更も失われます）")
    if branch_exists(name):
        print(f"  削除するブランチ: {branch}（{MAIN_BRANCH} に未マージのコミットも失われます）")
    if "--yes" not in flags:
        print("確認のみ行いました。実行するには --yes を付けてください。")
        return
    if wt.is_dir():
        run_git(["worktree", "remove", "--force", str(wt)])
    if branch_exists(name):
        run_git(["branch", "-D", branch])
    run_git(["worktree", "prune"])
    print(f"ABORTED: {name}")


def human_pending_of(name: str) -> list[str]:
    """残っている人のタスク。worktree があればその tasks.md、なければ main の tasks.md を読む。

    メインの作業ツリーが main にいるときは、コミット前の変更も含めて作業ツリーのファイルを読む。
    """
    tasks_file = worktree_of(name) / "specs" / name / "tasks.md"
    if tasks_file.is_file():
        return unchecked_tasks(tasks_file)[1]
    if git_out(["rev-parse", "--abbrev-ref", "HEAD"]) == MAIN_BRANCH:
        return unchecked_tasks(REPO_ROOT / "specs" / name / "tasks.md")[1]
    return split_unchecked(main_tasks_text(name))[1]


def cmd_status(_: list[str]) -> None:
    print("| FEATURE | 仕様 | 実装 | WORKTREE | 人の作業 |")
    print("|---|---|---|---|---|")
    for name in get_all_features():
        done = completed_steps(name)
        has_tasks = main_has_tasks(name)
        if has_tasks:
            spec_col = "完了"
        elif "S7-3" in done:
            spec_col = "完了（未マージ）"
        elif done:
            spec_col = "作業中"
        else:
            spec_col = "未着手"
        if coding_done(name):
            coding_col = "完了"
        elif "S8" in done or "S9" in done:
            coding_col = "作業中"
        elif "S7-3" in done:
            coding_col = "未着手"
        else:
            coding_col = "-"
        wt_col = f"あり（次: {next_step(name, 'all')}）" if worktree_of(name).is_dir() else "-"
        human = human_pending_of(name)
        human_col = f"残り {len(human)} 件" if human else "-"
        print(f"| {name} | {spec_col} | {coding_col} | {wt_col} | {human_col} |")


def cmd_human_tasks(args: list[str]) -> None:
    """残っている人のタスクを、フィーチャーごとに表示する。"""
    positional, _, _ = parse_args(args)
    names = [resolve_feature(positional)] if positional else get_all_features()
    for name in names:
        human = human_pending_of(name)
        if human:
            print(f"{name}:")
            for line in human:
                print(f"  {line}")


def cmd_sync_status(args: list[str]) -> None:
    """main にマージ済みのフィーチャーの状態欄を、main の tasks.md に合わせる（人のタスクを片付けた後に使う）。"""
    positional, _, _ = parse_args(args)
    name = resolve_feature(positional)
    if worktree_of(name).is_dir():
        raise HelperError(f"{name} の worktree があります。worktree の作業は checkpoint と finish で進めてください。")
    if not coding_done(name):
        raise HelperError(f"{name} は実装まで {MAIN_BRANCH} にマージされていません。")
    current = git_out(["rev-parse", "--abbrev-ref", "HEAD"])
    if current != MAIN_BRANCH:
        raise HelperError(f"{REPO_ROOT} のブランチが {current} です。{MAIN_BRANCH} で実行してください。")
    tasks_file = REPO_ROOT / "specs" / name / "tasks.md"
    status = status_after_coding(name, tasks_file)
    # 実装後の状態（完了 / 人の作業待ち）どうしでだけ動かし、それ以前の状態を飛び越えない。
    changed = update_feature_status(REPO_ROOT, name, status, only_from=(STATUS_DONE, "人の作業待ち"))
    for path in changed:
        info(f"==> 状態を更新しました: {path}（コミットはしていません）")
    print(f"FEATURE_STATUS: {status}")
    human = unchecked_tasks(tasks_file)[1]
    if human:
        print(f"HUMAN_TASKS_PENDING: {len(human)}")
        for line in human:
            print(f"  {line}")


def cmd_next(args: list[str]) -> None:
    _, phase, _ = parse_args(args)
    phase = require_phase(phase)
    skip: set[str] = set()
    for i, arg in enumerate(args):
        if arg == "--skip" and i + 1 < len(args):
            skip.update(resolve_feature(n) for n in args[i + 1].split(",") if n)
        elif arg.startswith("--skip="):
            skip.update(resolve_feature(n) for n in arg[len("--skip="):].split(",") if n)
    features = [f for f in get_all_features() if f not in skip]

    # 途中のまま残っている worktree を最優先にする。
    for name in features:
        if not worktree_of(name).is_dir():
            continue
        done = completed_steps(name)
        if (phase == "spec" and "S8" not in done) or (phase == "coding" and "S7-3" in done) or phase == "all":
            print(name)
            return

    for name in features:
        has_tasks = main_has_tasks(name)
        if phase == "spec" and not has_tasks:
            print(name)
            return
        if phase == "coding" and has_tasks and not coding_done(name):
            print(name)
            return
        if phase == "all" and (not has_tasks or not coding_done(name)):
            print(name)
            return
    print("")


def cmd_list(_: list[str]) -> None:
    for name in get_all_features():
        print(name)


def cmd_resolve(args: list[str]) -> None:
    print(resolve_feature(args[0] if args else None))


USAGE = f"""Usage: worktree_helper.py <command> [arguments]

Commands:
  ensure <feature> --phase spec|coding|all
        worktree があれば再利用し、なければ {MAIN_BRANCH} から作る。進捗と次のステップを表示する
  state <feature> --phase spec|coding|all
        変更せずに進捗と次のステップを表示する
  checkpoint <feature> <step> <subject>
        worktree の変更をすべてコミットし、trailer "Speckit-Step: <step>" と "Speckit-Feature: <feature>" で
        完了を記録する（変更がなくても空コミットで記録）。S2 と S11 では機能ファイルの状態欄も更新する
  finish <feature> --phase spec|coding|all [--allow-unchecked] [--commit-leftovers] [--switch]
        最終ステップの完了を確認し、{MAIN_BRANCH} に --no-ff でマージして worktree とブランチを削除する。
        worktree の外で実行する。coding / all では tasks.md に未完了があると止まる（--allow-unchecked で続行）。
        未完了が {HUMAN_MARKER} のタスクだけなら止めずにマージし、HUMAN_TASKS_PENDING で残りを表示する。
        どのステップにも含まれない変更があると止まる（--commit-leftovers で続行）。
        メインの作業ツリーが main 以外にいると止まる（--switch で main に切り替えて続行）
  abort <feature> [--yes]
        worktree とブランチを破棄する。--yes がなければ対象を表示するだけ
  list
        全フィーチャー名を着手順（spec_order.md の並び、その後に番号順）で表示する
  status
        全フィーチャーの仕様・実装・worktree の状況と、残っている人のタスクの件数を表示する
  human-tasks [<feature>]
        残っている {HUMAN_MARKER} のタスクを表示する（worktree があればその tasks.md、なければ {MAIN_BRANCH} のもの）
  sync-status <feature>
        {MAIN_BRANCH} にマージ済みのフィーチャーの状態欄を tasks.md に合わせる（完了 / 人の作業待ち）。
        人のタスクを片付けた後に {MAIN_BRANCH} で実行する。変更はコミットしない
  next --phase spec|coding|all [--skip <feature,...>]
        次に着手すべきフィーチャーを表示する（途中の worktree を優先。--skip で除外）
  resolve <query>
        番号やスラッグからフィーチャー名を決める

Steps: {' '.join(ALL_STEPS)}（S1 は ensure、S12 は finish）
Exit codes: 0 = 成功, 1 = エラー, 3 = 前提条件を満たさない（PRECONDITION: <code> を stderr に出力）
Environment: SPECKIT_MAIN_BRANCH（既定のブランチ名。既定値 main）
             CLAUDE_CODE_REMOTE=true（Claude Code のクラウドセッション。SPECKIT_MAIN_BRANCH がなければ、
             メインの作業ツリーの今のブランチをマージ先にし、finish の後に origin へ push する）"""

COMMANDS = {
    "ensure": cmd_ensure,
    "state": cmd_state,
    "checkpoint": cmd_checkpoint,
    "finish": cmd_finish,
    "merge": cmd_finish,
    "abort": cmd_abort,
    "list": cmd_list,
    "status": cmd_status,
    "human-tasks": cmd_human_tasks,
    "sync-status": cmd_sync_status,
    "next": cmd_next,
    "resolve": cmd_resolve,
}


def main(argv: list[str]) -> int:
    global REPO_ROOT, WORKTREES_DIR, MAIN_BRANCH
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    action = argv[0] if argv else "help"
    if action in ("help", "-h", "--help"):
        print(USAGE)
        return 0
    command = COMMANDS.get(action)
    try:
        if command is None:
            raise HelperError(f"不明なコマンド '{action}' です。'worktree_helper.py help' で使い方を確認してください。")
        REPO_ROOT = find_repo_root()
        WORKTREES_DIR = REPO_ROOT / ".worktrees"
        MAIN_BRANCH = resolve_main_branch()
        if not git_ok(["rev-parse", "--verify", "-q", f"refs/heads/{MAIN_BRANCH}"]):
            raise HelperError(
                f"ブランチ {MAIN_BRANCH} がありません。既定のブランチが別の名前なら、環境変数 SPECKIT_MAIN_BRANCH にその名前を指定してください。")
        command(argv[1:])
    except Precondition as stop:
        print(f"PRECONDITION: {stop.code}", file=sys.stderr)
        print(str(stop), file=sys.stderr)
        return 3
    except HelperError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""worktree_helper.py - speckit-feature / speckit-coding / speckit-all 共通の worktree 管理

各フィーチャーを .worktrees/<FEATURE_NAME>（ブランチ feature/<FEATURE_NAME>）で作業し、
ステップ完了ごとのコミットに付けた trailer "Speckit-Step: <STEP>" で進捗を判定する。
プロジェクトのルートから実行しても worktree の中から実行しても同じように動く。
macOS / Linux / Windows で動くように、標準ライブラリだけで書く（Python 3.9 以上）。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

MAIN_BRANCH = os.environ.get("SPECKIT_MAIN_BRANCH", "main")
SPEC_STEPS = ["S2", "S3", "S4", "S5", "S6", "S7-1", "S7-2", "S7-3"]
CODING_STEPS = ["S8", "S9", "S10", "S11"]
ALL_STEPS = SPEC_STEPS + CODING_STEPS
PHASE_STEPS = {"spec": SPEC_STEPS, "coding": CODING_STEPS, "all": ALL_STEPS}
PHASE_LAST_STEP = {"spec": "S7-3", "coding": "S11", "all": "S11"}
# feature.json はローカル状態なので、.gitignore の設定にかかわらずコミットしない。
FEATURE_JSON = ".specify/feature.json"
ORDER_LINE_RE = re.compile(r"\*\*\s*([0-9]+)\.\s*\[[^\]]*\]\(\./([^.)]+)\.md\)")
TRAILER_RE = re.compile(r"^Speckit-Step:\s*(\S+)", re.MULTILINE)
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
    """worktree の中から実行しても、メインの作業ツリーのルートを返す。"""
    proc = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise HelperError("Git リポジトリの中で実行してください。")
    common = Path(proc.stdout.strip())
    if not common.is_absolute():
        common = Path.cwd() / common
    return common.resolve().parent


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


def main_tasks_unchecked(name: str) -> bool:
    proc = run_git(["show", f"{MAIN_BRANCH}:specs/{name}/tasks.md"], check=False)
    if proc.returncode != 0:
        return False
    return re.search(r"^[ \t]*- \[ \]", proc.stdout, re.MULTILINE) is not None


def completed_steps(name: str) -> list[str]:
    """完了済みのステップ。ブランチ上の trailer に加え、仕様が main にマージ済みなら S2〜S7-3 を完了とみなす。"""
    found: set[str] = set()
    if branch_exists(name):
        log = git_out(["log", f"{MAIN_BRANCH}..{branch_of(name)}", "--format=%B"])
        found.update(TRAILER_RE.findall(log))
    if main_has_tasks(name):
        found.update(SPEC_STEPS)
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
    """docs/feature/spec_order.md（任意）、main の specs/、.worktrees/ からフィーチャー名を集める。"""
    names: set[str] = set()
    for match in ORDER_LINE_RE.finditer(read_spec_order()):
        num, slug = match.group(1), match.group(2)
        # 新形式はファイル名が NNN-slug で、そのまま specs/ の名前になる。旧形式は slug だけなので番号を付ける。
        if re.match(r"^[0-9]{3}-", slug):
            names.add(slug)
        else:
            names.add(f"{int(num):03d}-{slug}")
    proc = run_git(["ls-tree", "-d", "--name-only", MAIN_BRANCH, "specs/"], check=False)
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            if line.startswith("specs/"):
                names.add(line[len("specs/"):])
    if WORKTREES_DIR.is_dir():
        for child in WORKTREES_DIR.iterdir():
            if child.is_dir():
                names.add(child.name)
    return sorted(n for n in names if n)


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


def print_state(name: str, phase: str, wt_state: str) -> None:
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
    if (phase != "spec" and not wt.is_dir() and not branch_exists(name)
            and main_has_tasks(name) and not main_tasks_unchecked(name)):
        raise Precondition("ALREADY_IMPLEMENTED", f"{name} は {MAIN_BRANCH} の tasks.md がすべて完了済みです。")


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

    stage_all(wt)
    run_git(["commit", "-q", "--allow-empty", "-m", subject, "-m", f"Speckit-Step: {step}"], cwd=wt)
    print(f"CHECKPOINT: {step} {git_out(['rev-parse', '--short', 'HEAD'], cwd=wt)}")
    print(f"NEXT_STEP: {next_step(name, 'all')}")


def cmd_finish(args: list[str]) -> None:
    positional, phase, _ = parse_args(args)
    phase = require_phase(phase)
    name = resolve_feature(positional)
    branch = branch_of(name)
    wt = worktree_of(name)
    last = PHASE_LAST_STEP[phase]

    if not wt.is_dir():
        raise HelperError(f"worktree {wt} がありません。")
    if last not in completed_steps(name):
        raise HelperError(f"{phase} 工程の最終ステップ {last} が完了していません（次: {next_step(name, phase)}）。")
    for filename in ("spec.md", "plan.md", "tasks.md"):
        if not (wt / "specs" / name / filename).is_file():
            raise HelperError(f"{wt / 'specs' / name / filename} がありません。")

    stage_all(wt)
    if not git_ok(["diff", "--cached", "--quiet"], cwd=wt):
        info("==> worktree の未コミットの変更をコミットします。")
        run_git(["commit", "-q", "-m", f"chore({name}): finalize remaining changes before merge"], cwd=wt)

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
        info(f"==> {REPO_ROOT} を {MAIN_BRANCH} に切り替えます（現在: {current}）。")
        run_git(["checkout", "-q", MAIN_BRANCH])

    info(f"==> {branch} を {MAIN_BRANCH} に --no-ff でマージします。")
    try:
        git_passthrough(["merge", "--no-ff", "-m", f"merge({name}): {phase}", branch])
    except HelperError as error:
        raise HelperError(
            f"マージで競合しました。{REPO_ROOT} で競合を解消してマージをコミットし、"
            "もう一度 finish を実行してください（worktree とブランチは残しています）。"
        ) from error

    info("==> worktree とブランチを削除します。")
    # 変更はすべてマージ済みで、残るのは無視対象のローカル状態（feature.json など）だけなので --force で削除する。
    run_git(["worktree", "remove", "--force", str(wt)])
    git_passthrough(["branch", "-d", branch])
    print(f"FINISHED: {name} ({phase})")
    print(f"MERGE_COMMIT: {git_out(['rev-parse', '--short', 'HEAD'])}")


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


def cmd_status(_: list[str]) -> None:
    print("| FEATURE | 仕様 | 実装 | WORKTREE |")
    print("|---|---|---|---|")
    for name in get_all_features():
        done = completed_steps(name)
        has_tasks = main_has_tasks(name)
        if has_tasks:
            spec_col = "完了"
        elif done:
            spec_col = "作業中"
        else:
            spec_col = "未着手"
        if has_tasks and not main_tasks_unchecked(name):
            coding_col = "完了"
        elif "S8" in done or "S9" in done:
            coding_col = "作業中"
        elif "S7-3" in done:
            coding_col = "未着手"
        else:
            coding_col = "-"
        wt_col = f"あり（次: {next_step(name, 'all')}）" if worktree_of(name).is_dir() else "-"
        print(f"| {name} | {spec_col} | {coding_col} | {wt_col} |")


def cmd_next(args: list[str]) -> None:
    _, phase, _ = parse_args(args)
    phase = require_phase(phase)
    features = get_all_features()

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
        if phase == "coding" and has_tasks and main_tasks_unchecked(name):
            print(name)
            return
        if phase == "all" and (not has_tasks or main_tasks_unchecked(name)):
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
        worktree の変更をすべてコミットし、trailer "Speckit-Step: <step>" で完了を記録する（変更がなくても空コミットで記録）
  finish <feature> --phase spec|coding|all
        最終ステップの完了を確認し、{MAIN_BRANCH} に --no-ff でマージして worktree とブランチを削除する
  abort <feature> [--yes]
        worktree とブランチを破棄する。--yes がなければ対象を表示するだけ
  list
        全フィーチャー名を番号順に表示する（範囲指定の展開に使う）
  status
        全フィーチャーの仕様・実装・worktree の状況を表示する
  next --phase spec|coding|all
        次に着手すべきフィーチャーを表示する（途中の worktree を優先）
  resolve <query>
        番号やスラッグからフィーチャー名を決める

Steps: {' '.join(ALL_STEPS)}（S1 は ensure、S12 は finish）
Exit codes: 0 = 成功, 1 = エラー, 3 = 前提条件を満たさない（PRECONDITION: <code> を stderr に出力）"""

COMMANDS = {
    "ensure": cmd_ensure,
    "state": cmd_state,
    "checkpoint": cmd_checkpoint,
    "finish": cmd_finish,
    "merge": cmd_finish,
    "abort": cmd_abort,
    "list": cmd_list,
    "status": cmd_status,
    "next": cmd_next,
    "resolve": cmd_resolve,
}


def main(argv: list[str]) -> int:
    global REPO_ROOT, WORKTREES_DIR
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

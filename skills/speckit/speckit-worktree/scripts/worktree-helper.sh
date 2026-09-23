#!/usr/bin/env bash
# worktree-helper.sh - speckit-feature / speckit-coding / speckit-all 共通の worktree 管理
#
# 各フィーチャーを .worktrees/<FEATURE_NAME>（ブランチ feature/<FEATURE_NAME>）で作業し、
# ステップ完了ごとのコミットに付けた trailer "Speckit-Step: <STEP>" で進捗を判定する。
# プロジェクトのルートから実行しても worktree の中から実行しても同じように動く。
# macOS 標準の bash 3.2 で動くように書く（mapfile や連想配列は使わない）。

set -euo pipefail

MAIN_BRANCH="${SPECKIT_MAIN_BRANCH:-main}"
ALL_STEPS="S2 S3 S4 S5 S6 S7-1 S7-2 S7-3 S8 S9 S10 S11"
SPEC_STEPS="S2 S3 S4 S5 S6 S7-1 S7-2 S7-3"
CODING_STEPS="S8 S9 S10 S11"

die() {
    echo "ERROR: $*" >&2
    exit 1
}

# 前提条件を満たさないときの停止。スキル側で案内を出すため終了コードを分ける。
stop_precondition() {
    local code="$1"
    shift
    echo "PRECONDITION: $code" >&2
    echo "$*" >&2
    exit 3
}

# worktree の中から実行しても、メインの作業ツリーのルートを返す。
repo_root() {
    local common
    common=$(git rev-parse --git-common-dir 2>/dev/null) || die "Git リポジトリの中で実行してください。"
    (CDPATH="" cd "$common/.." && pwd -P)
}

# help 以外のコマンドを実行するときに設定する。
REPO_ROOT=""
WORKTREES_DIR=""

g() {
    git -C "$REPO_ROOT" "$@"
}

branch_of() { echo "feature/$1"; }
worktree_of() { echo "$WORKTREES_DIR/$1"; }

branch_exists() {
    g rev-parse --verify -q "refs/heads/$(branch_of "$1")" >/dev/null
}

main_has_file() {
    g cat-file -e "$MAIN_BRANCH:specs/$1/$2" 2>/dev/null
}

main_has_tasks() {
    main_has_file "$1" tasks.md
}

main_has_all_artifacts() {
    main_has_file "$1" spec.md && main_has_file "$1" plan.md && main_has_file "$1" tasks.md
}

main_tasks_unchecked() {
    # grep -q の早期終了で git show が SIGPIPE になり pipefail で偽になるのを避けるため、先に変数へ取り込む。
    local content
    content=$(g show "$MAIN_BRANCH:specs/$1/tasks.md" 2>/dev/null) || return 1
    grep -Eq '^[[:space:]]*- \[ \]' <<<"$content"
}

phase_steps() {
    case "$1" in
        spec) echo "$SPEC_STEPS" ;;
        coding) echo "$CODING_STEPS" ;;
        all) echo "$ALL_STEPS" ;;
        *) die "--phase には spec / coding / all のいずれかを指定してください（指定値: '$1'）。" ;;
    esac
}

phase_last_step() {
    case "$1" in
        spec) echo "S7-3" ;;
        coding | all) echo "S11" ;;
        *) phase_steps "$1" >/dev/null ;;
    esac
}

contains_word() {
    local needle="$1" word
    shift
    for word in $*; do
        [[ "$word" == "$needle" ]] && return 0
    done
    return 1
}

# 完了済みのステップ。ブランチ上の trailer に加え、仕様が main にマージ済みなら S2〜S7-3 を完了とみなす。
completed_steps() {
    local name="$1" found="" step result=""
    if branch_exists "$name"; then
        found=$(g log "$MAIN_BRANCH..$(branch_of "$name")" --format=%B |
            sed -n 's/^Speckit-Step:[[:space:]]*\([^[:space:]]*\).*/\1/p')
    fi
    if main_has_tasks "$name"; then
        found="$found $SPEC_STEPS"
    fi
    for step in $ALL_STEPS; do
        if contains_word "$step" $found; then
            result="$result $step"
        fi
    done
    echo "${result# }"
}

next_step() {
    local name="$1" phase="$2" done_steps step
    done_steps="$(completed_steps "$name")"
    for step in $(phase_steps "$phase"); do
        if ! contains_word "$step" $done_steps; then
            echo "$step"
            return 0
        fi
    done
    echo "S12"
}

# docs/feature/spec_order.md（任意）、main の specs/、.worktrees/ からフィーチャー名を集める。
get_all_features() {
    local spec_order line num slug formatted dir
    {
        spec_order=$(g show "$MAIN_BRANCH:docs/feature/spec_order.md" 2>/dev/null ||
            cat "$REPO_ROOT/docs/feature/spec_order.md" 2>/dev/null || true)
        if [[ -n "$spec_order" ]]; then
            while IFS= read -r line; do
                # 例: - **1. [名前](./data-persistence-core.md)**（番号なしのファイル名）
                # 例: - **1. [名前](./001-data-persistence-core.md)**（番号付きのファイル名。二重に番号を付けない）
                if [[ "$line" =~ \*\*[[:space:]]*([0-9]+)\.[[:space:]]*\[[^]]*\]\(\./([^.]+)\.md\) ]]; then
                    num="${BASH_REMATCH[1]}"
                    slug="${BASH_REMATCH[2]}"
                    printf -v formatted "%03d" "$((10#$num))"
                    if [[ "$slug" =~ ^[0-9]{3}- ]]; then
                        echo "$slug"
                    else
                        echo "${formatted}-${slug}"
                    fi
                fi
            done <<<"$spec_order"
        fi
        g ls-tree -d --name-only "$MAIN_BRANCH" specs/ 2>/dev/null | sed 's#^specs/##'
        if [[ -d "$WORKTREES_DIR" ]]; then
            for dir in "$WORKTREES_DIR"/*; do
                if [[ -d "$dir" ]]; then
                    basename "$dir"
                fi
            done
        fi
    } | sed '/^$/d' | sort -u
}

# 短い番号（1, 002）、スラッグ、完全名（001-todo-cli）、ファイルパスからフィーチャー名を決める。
resolve_feature() {
    local query="${1:-}" padded feat
    [[ -n "$query" ]] || die "フィーチャーを指定してください。"
    query="$(basename "$query")"
    query="${query%.md}"
    padded="$query"
    if [[ "$query" =~ ^[0-9]+$ ]]; then
        printf -v padded "%03d" "$((10#$query))"
    fi

    local matches=()
    while IFS= read -r feat; do
        [[ -z "$feat" ]] && continue
        if [[ "$feat" == "$query" ]]; then
            echo "$feat"
            return 0
        fi
        if [[ "$feat" == "${padded}-"* || "$feat" == *"-${query}" ]]; then
            matches+=("$feat")
        fi
    done < <(get_all_features)

    if [[ ${#matches[@]} -eq 1 ]]; then
        echo "${matches[0]}"
        return 0
    elif [[ ${#matches[@]} -gt 1 ]]; then
        die "'$query' に一致するフィーチャーが複数あります: ${matches[*]}"
    fi

    # 一覧にない新しいフィーチャーは、完全名（NNN-slug）で指定されたときだけ受け付ける。
    if [[ "$query" =~ ^[0-9]{3}-[a-z0-9][a-z0-9-]*$ ]]; then
        echo "$query"
        return 0
    fi
    die "'$query' に一致するフィーチャーが見つかりません（docs/feature/spec_order.md、specs/、.worktrees/ を検索）。新しいフィーチャーは 001-short-name の形の完全名で指定してください。"
}

# feature.json はローカル状態なので、.gitignore の設定にかかわらずコミットしない。
stage_all() {
    git -C "$1" add -A
    git -C "$1" reset -q -- .specify/feature.json 2>/dev/null || true
}

print_state() {
    local name="$1" phase="$2" wt_state="$3"
    echo "FEATURE_NAME: $name"
    echo "BRANCH: $(branch_of "$name")"
    echo "WORKTREE_DIR: $(worktree_of "$name")"
    echo "WORKTREE_STATE: $wt_state"
    echo "PHASE: $phase"
    echo "COMPLETED_STEPS: $(completed_steps "$name")"
    echo "NEXT_STEP: $(next_step "$name" "$phase")"
}

parse_phase() {
    local phase=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --phase) phase="${2:-}"; shift 2 ;;
            --phase=*) phase="${1#--phase=}"; shift ;;
            *) shift ;;
        esac
    done
    [[ -n "$phase" ]] || die "--phase spec|coding|all を指定してください。"
    phase_steps "$phase" >/dev/null
    echo "$phase"
}

first_positional() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --phase) shift 2 ;;
            --*) shift ;;
            *) echo "$1"; return 0 ;;
        esac
    done
}

check_phase_precondition() {
    local name="$1" phase="$2" wt="$3" done_steps
    done_steps="$(completed_steps "$name")"
    case "$phase" in
        spec)
            if [[ ! -d "$wt" ]] && main_has_tasks "$name"; then
                stop_precondition ALREADY_SPECIFIED \
                    "$name の仕様（tasks.md）はすでに $MAIN_BRANCH にマージされています。実装は speckit-coding で行ってください。"
            fi
            if contains_word S8 $done_steps; then
                stop_precondition CODING_IN_PROGRESS \
                    "$name の worktree はすでに実装工程に入っています。speckit-coding または speckit-all で再開してください。"
            fi
            ;;
        coding)
            if ! contains_word S7-3 $done_steps; then
                if [[ -d "$wt" ]] || branch_exists "$name"; then
                    stop_precondition SPEC_INCOMPLETE \
                        "$name の仕様工程（S2〜S7-3）が終わっていません（次: $(next_step "$name" spec)）。speckit-feature または speckit-all で再開してください。"
                fi
                stop_precondition SPEC_MISSING \
                    "$name の spec.md / plan.md / tasks.md が $MAIN_BRANCH にも worktree にもありません。先に speckit-feature または speckit-all を実行してください。"
            fi
            if [[ ! -d "$wt" ]] && ! main_has_all_artifacts "$name"; then
                stop_precondition SPEC_MISSING \
                    "$name の spec.md / plan.md / tasks.md が $MAIN_BRANCH にそろっていません。先に speckit-feature または speckit-all を実行してください。"
            fi
            ;;
    esac
    if [[ ! -d "$wt" ]] && ! branch_exists "$name" && main_has_tasks "$name" && ! main_tasks_unchecked "$name" && [[ "$phase" != spec ]]; then
        stop_precondition ALREADY_IMPLEMENTED \
            "$name は $MAIN_BRANCH の tasks.md がすべて完了済みです。"
    fi
}

cmd_ensure() {
    local phase name branch wt wt_state
    phase="$(parse_phase "$@")"
    name="$(resolve_feature "$(first_positional "$@")")"
    branch="$(branch_of "$name")"
    wt="$(worktree_of "$name")"

    g worktree prune
    check_phase_precondition "$name" "$phase" "$wt"

    if [[ -d "$wt" ]]; then
        local wt_branch
        wt_branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null) ||
            die "$wt は Git の worktree ではありません。手動で確認してください。"
        [[ "$wt_branch" == "$branch" ]] ||
            die "$wt のブランチが '$wt_branch' です（期待値: '$branch'）。手動で確認してください。"
        wt_state="reused"
    else
        g check-ignore -q .worktrees/ ||
            die ".worktrees/ が .gitignore に登録されていません。.gitignore に '.worktrees/' を追加してコミットしてから再実行してください。"
        if [[ -n "$(g status --porcelain)" ]]; then
            g status --short >&2
            die "$REPO_ROOT に未コミットの変更があります。コミットまたは stash してから再実行してください。"
        fi
        mkdir -p "$WORKTREES_DIR"
        if branch_exists "$name"; then
            echo "==> 既存のブランチ $branch に worktree を作り直します: $wt" >&2
            g worktree add "$wt" "$branch" >&2
            wt_state="reattached"
        else
            echo "==> $MAIN_BRANCH から $branch と worktree を作成します: $wt" >&2
            g worktree add -b "$branch" "$wt" "$MAIN_BRANCH" >&2
            wt_state="created"
        fi
    fi

    # feature.json は .specify/.gitignore で除外されるローカル状態。speckit の各スキルが対象ディレクトリの特定に使う。
    mkdir -p "$wt/.specify" "$wt/specs/$name"
    printf '{\n  "feature_directory": "specs/%s"\n}\n' "$name" >"$wt/.specify/feature.json"

    print_state "$name" "$phase" "$wt_state"
}

cmd_state() {
    local phase name wt
    phase="$(parse_phase "$@")"
    name="$(resolve_feature "$(first_positional "$@")")"
    wt="$(worktree_of "$name")"
    if [[ -d "$wt" ]]; then
        print_state "$name" "$phase" present
    else
        print_state "$name" "$phase" absent
    fi
}

cmd_checkpoint() {
    local name step subject wt wt_branch
    [[ $# -ge 3 ]] || die "使い方: checkpoint <feature> <step> <subject>"
    name="$(resolve_feature "$1")"
    step="$2"
    subject="$3"
    contains_word "$step" $ALL_STEPS || die "ステップ '$step' は不正です（有効値: ${ALL_STEPS}）。"
    wt="$(worktree_of "$name")"
    [[ -d "$wt" ]] || die "worktree $wt がありません。先に ensure を実行してください。"
    wt_branch=$(git -C "$wt" rev-parse --abbrev-ref HEAD)
    [[ "$wt_branch" == "$(branch_of "$name")" ]] || die "$wt のブランチが '$wt_branch' です。"

    stage_all "$wt"
    git -C "$wt" commit -q --allow-empty -m "$subject" -m "Speckit-Step: $step"
    echo "CHECKPOINT: $step $(git -C "$wt" rev-parse --short HEAD)"
    echo "NEXT_STEP: $(next_step "$name" all)"
}

cmd_finish() {
    local phase name branch wt last current
    phase="$(parse_phase "$@")"
    name="$(resolve_feature "$(first_positional "$@")")"
    branch="$(branch_of "$name")"
    wt="$(worktree_of "$name")"
    last="$(phase_last_step "$phase")"

    [[ -d "$wt" ]] || die "worktree $wt がありません。"
    contains_word "$last" $(completed_steps "$name") ||
        die "$phase 工程の最終ステップ $last が完了していません（次: $(next_step "$name" "$phase")）。"
    for f in spec.md plan.md tasks.md; do
        [[ -f "$wt/specs/$name/$f" ]] || die "$wt/specs/$name/$f がありません。"
    done

    stage_all "$wt"
    if ! git -C "$wt" diff --cached --quiet; then
        echo "==> worktree の未コミットの変更をコミットします。" >&2
        git -C "$wt" commit -q -m "chore($name): finalize remaining changes before merge"
    fi

    # マージ後の片付けで止まらないよう、マージの前に worktree がクリーンであることを確かめる。
    if [[ -n "$(git -C "$wt" status --porcelain -- . ':(exclude).specify/feature.json')" ]]; then
        git -C "$wt" status --short >&2
        die "$wt にコミットできない変更が残っています。確認してから再実行してください。"
    fi
    if [[ -n "$(g status --porcelain)" ]]; then
        g status --short >&2
        die "$REPO_ROOT に未コミットの変更があるためマージできません。コミットまたは stash してから再実行してください。"
    fi
    current=$(g rev-parse --abbrev-ref HEAD)
    if [[ "$current" != "$MAIN_BRANCH" ]]; then
        echo "==> $REPO_ROOT を $MAIN_BRANCH に切り替えます（現在: ${current}）。" >&2
        g checkout -q "$MAIN_BRANCH"
    fi

    echo "==> $branch を $MAIN_BRANCH に --no-ff でマージします。" >&2
    if ! g merge --no-ff -m "merge($name): $phase" "$branch" >&2; then
        die "マージで競合しました。$REPO_ROOT で競合を解消してマージをコミットし、もう一度 finish を実行してください（worktree とブランチは残しています）。"
    fi

    echo "==> worktree とブランチを削除します。" >&2
    # 変更はすべてマージ済みで、残るのは無視対象のローカル状態（feature.json など）だけなので --force で削除する。
    g worktree remove --force "$wt"
    g branch -d "$branch" >&2

    echo "FINISHED: $name ($phase)"
    echo "MERGE_COMMIT: $(g rev-parse --short HEAD)"
}

cmd_abort() {
    local name branch wt yes=0 arg
    for arg in "$@"; do
        [[ "$arg" == "--yes" ]] && yes=1
    done
    name="$(resolve_feature "$(first_positional "$@")")"
    branch="$(branch_of "$name")"
    wt="$(worktree_of "$name")"

    echo "対象: $name"
    [[ -d "$wt" ]] && echo "  削除する worktree: ${wt}（未コミットの変更も失われます）"
    branch_exists "$name" && echo "  削除するブランチ: ${branch}（$MAIN_BRANCH に未マージのコミットも失われます）"
    if [[ $yes -ne 1 ]]; then
        echo "確認のみ行いました。実行するには --yes を付けてください。"
        return 0
    fi

    if [[ -d "$wt" ]]; then
        g worktree remove --force "$wt"
    fi
    if branch_exists "$name"; then
        g branch -D "$branch"
    fi
    g worktree prune
    echo "ABORTED: $name"
}

cmd_status() {
    local name spec_col coding_col wt_col done_steps
    echo "| FEATURE | 仕様 | 実装 | WORKTREE |"
    echo "|---|---|---|---|"
    while IFS= read -r name; do
        [[ -z "$name" ]] && continue
        done_steps="$(completed_steps "$name")"
        if main_has_tasks "$name"; then
            spec_col="完了"
        elif [[ -n "$done_steps" ]]; then
            spec_col="作業中"
        else
            spec_col="未着手"
        fi
        if main_has_tasks "$name" && ! main_tasks_unchecked "$name"; then
            coding_col="完了"
        elif contains_word S8 $done_steps || contains_word S9 $done_steps; then
            coding_col="作業中"
        elif contains_word S7-3 $done_steps; then
            coding_col="未着手"
        else
            coding_col="-"
        fi
        if [[ -d "$(worktree_of "$name")" ]]; then
            wt_col="あり（次: $(next_step "$name" all)）"
        else
            wt_col="-"
        fi
        echo "| $name | $spec_col | $coding_col | $wt_col |"
    done < <(get_all_features)
}

cmd_next() {
    local phase name done_steps
    phase="$(parse_phase "$@")"
    local features
    features="$(get_all_features)"

    # 途中のまま残っている worktree を最優先にする。
    while IFS= read -r name; do
        [[ -z "$name" || ! -d "$(worktree_of "$name")" ]] && continue
        done_steps="$(completed_steps "$name")"
        case "$phase" in
            spec) contains_word S8 $done_steps || { echo "$name"; return 0; } ;;
            coding) contains_word S7-3 $done_steps && { echo "$name"; return 0; } ;;
            all) echo "$name"; return 0 ;;
        esac
    done <<<"$features"

    while IFS= read -r name; do
        [[ -z "$name" ]] && continue
        case "$phase" in
            spec)
                main_has_tasks "$name" || { echo "$name"; return 0; } ;;
            coding)
                if main_has_tasks "$name" && main_tasks_unchecked "$name"; then
                    echo "$name"; return 0
                fi ;;
            all)
                if ! main_has_tasks "$name" || main_tasks_unchecked "$name"; then
                    echo "$name"; return 0
                fi ;;
        esac
    done <<<"$features"
    echo ""
}

usage() {
    cat <<EOF
Usage: $0 <command> [arguments]

Commands:
  ensure <feature> --phase spec|coding|all
        worktree があれば再利用し、なければ $MAIN_BRANCH から作る。進捗と次のステップを表示する
  state <feature> --phase spec|coding|all
        変更せずに進捗と次のステップを表示する
  checkpoint <feature> <step> <subject>
        worktree の変更をすべてコミットし、trailer "Speckit-Step: <step>" で完了を記録する（変更がなくても空コミットで記録）
  finish <feature> --phase spec|coding|all
        最終ステップの完了を確認し、$MAIN_BRANCH に --no-ff でマージして worktree とブランチを削除する
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

Steps: ${ALL_STEPS}（S1 は ensure、S12 は finish）
Exit codes: 0 = 成功, 1 = エラー, 3 = 前提条件を満たさない（PRECONDITION: <code> を stderr に出力）
EOF
}

ACTION="${1:-help}"
shift || true

case "$ACTION" in
    help | -h | --help) ;;
    *)
        REPO_ROOT="$(repo_root)"
        WORKTREES_DIR="$REPO_ROOT/.worktrees"
        ;;
esac

case "$ACTION" in
    ensure) cmd_ensure "$@" ;;
    state) cmd_state "$@" ;;
    checkpoint) cmd_checkpoint "$@" ;;
    finish) cmd_finish "$@" ;;
    abort) cmd_abort "$@" ;;
    list) get_all_features ;;
    status) cmd_status ;;
    next) cmd_next "$@" ;;
    resolve) resolve_feature "$@" ;;
    help | -h | --help) usage ;;
    *) die "不明なコマンド '$ACTION' です。'$0 help' で使い方を確認してください。" ;;
esac

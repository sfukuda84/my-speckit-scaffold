---
name: "speckit-worktree"
description: "speckit-feature・speckit-coding・speckit-all が共通で使う worktree 管理スキル。フィーチャーごとの Git worktree とブランチの準備（既存があれば再利用）、ステップ完了ごとの進捗コミット、main への --no-ff マージと片付け、中止、進捗の確認を行う。3 スキル共通の実行規則（ステップ番号、再開、安全規則、対話、引数の解釈、自動モード --auto）もここに定める。「フィーチャーの進捗を見せて」「worktree を破棄して」と言われたとき、または /speckit-worktree と打たれたときにも使う。"
argument-hint: "status | next --phase spec|coding|all | human-tasks [<フィーチャー>] | sync-status <フィーチャー> | abort <フィーチャー>"
compatibility: "Requires git and Python 3.9+, spec-kit project structure with .specify/ directory"
user-invocable: true
disable-model-invocation: false
---

# speckit-worktree スキル（worktree 管理と共通実行規則）

`speckit-feature`（仕様工程）、`speckit-coding`（実装工程）、`speckit-all`（通し）の 3 スキルが共通で使う。フィーチャーの作業はすべて `.worktrees/<FEATURE_NAME>`（ブランチ `feature/<FEATURE_NAME>`）で行い、ステップが終わるたびにコミットして進捗を記録する。中断しても、どのスキルからでも続きのステップから再開できる。

Claude Code、Codex CLI、Antigravity、Kiro CLI、opencode のいずれでも同じ手順で動く。

## 1. ヘルパースクリプト

```bash
python3 <skills>/speckit-worktree/scripts/worktree_helper.py <command> ...
```

以降、この呼び出しを `$HELPER` と書く。

- `<skills>` は、このスキルが置かれた skills ディレクトリ（`.claude/skills`、`.agents/skills`、`.kiro/skills` のいずれか）である。
- スクリプトは Python 3.9 以上の標準ライブラリだけで書かれており、macOS、Linux、Windows で動く。プロジェクトのルートからでも worktree の中からでも実行できる。
- `python3` がない環境（Windows など）では、`python` または `py -3` に読み替える。

| コマンド | 用途 |
|---|---|
| `$HELPER ensure <feature> --phase spec\|coding\|all` | S1 準備。worktree があれば再利用し、なければ `main` から作る |
| `$HELPER state <feature> --phase spec\|coding\|all` | 変更せずに進捗を表示する |
| `$HELPER checkpoint <feature> <step> "<subject>"` | worktree の変更をすべてコミットし、ステップの完了を記録する |
| `$HELPER finish <feature> --phase spec\|coding\|all [--allow-unchecked] [--commit-leftovers] [--switch]` | S12 片付け。`main` に `--no-ff` でマージし、worktree とブランチを削除する。worktree の外で実行する |
| `$HELPER abort <feature> [--yes]` | worktree とブランチを破棄する。`--yes` がなければ対象を表示するだけ |
| `$HELPER list` | 全フィーチャー名を着手順（`spec_order.md` の並び、その後に番号順）で表示する |
| `$HELPER status` | 全フィーチャーの仕様・実装・worktree の状況と、残っている人のタスク（`[人]`）の件数を表示する |
| `$HELPER human-tasks [<feature>]` | 残っている人のタスクを一覧する。worktree があればその `tasks.md`、なければ `main` のもの（メインの作業ツリーが `main` にいれば、コミット前の変更も含む）を読む |
| `$HELPER sync-status <feature>` | `main` にマージ済みのフィーチャーの状態欄を、`tasks.md` に合わせて `完了` か `人の作業待ち` にする。`main` で実行し、変更はコミットしない |
| `$HELPER next --phase spec\|coding\|all [--skip <feature,...>]` | 次に着手すべきフィーチャーを表示する（途中の worktree を優先。`--skip` で除外） |
| `$HELPER resolve <query>` | 番号やスラッグからフィーチャー名を決める |

`ensure` と `state` は次の形で結果を出力する。

```text
REPO_ROOT: /path/to/repo
FEATURE_NAME: 001-todo-cli
BRANCH: feature/001-todo-cli
WORKTREE_DIR: /path/to/repo/.worktrees/001-todo-cli
WORKTREE_STATE: created | reused | reattached | present | absent
PHASE: spec
COMPLETED_STEPS: S2 S3
NEXT_STEP: S4
```

終了コードは、0 が成功、1 がエラー、3 が前提条件を満たさないことを表す。3 のときは標準エラーに `PRECONDITION: <code>` と案内文が出る。

| code | 意味 | 対応 |
|---|---|---|
| `ALREADY_SPECIFIED` | 仕様はすでに `main` にマージ済み | `speckit-coding` を案内する |
| `ALREADY_IMPLEMENTED` | `main` の `tasks.md` がすべて完了済み | そのフィーチャーは完了として扱う |
| `CODING_IN_PROGRESS` | worktree がすでに実装工程に入っている | `speckit-coding` か `speckit-all` での再開を案内する |
| `SPEC_INCOMPLETE` | worktree の仕様工程が途中 | `speckit-feature` か `speckit-all` での再開を案内する |
| `SPEC_MISSING` | spec・plan・tasks がどこにもない | `speckit-feature` か `speckit-all` を案内する |
| `LEFTOVER_CHANGES` | `finish` で、worktree にどのステップのコミットにも含まれていない変更がある | 変更の一覧をユーザーに示す。マージに含めてよければ `--commit-leftovers` を付けて再実行する。含めない変更は、ユーザーの了承を得て取り除く |
| `NOT_ON_MAIN` | `finish` で、メインの作業ツリーが `main` 以外のブランチにいる | 切り替えてよいかをユーザーに確認し、よければ `--switch` を付けて再実行する |
| `UNCHECKED_TASKS` | `finish`（coding / all）で、`tasks.md` に `[人]` 以外の未完了のタスクが残っている | 未完了のタスクの一覧をユーザーに示す。実装するなら S8 の手順で片付けてから、残したままマージしてよいと確認できたら `--allow-unchecked` を付けて `finish` を再実行する |

`finish`（coding / all）は、未完了のタスクが `[人]` のものだけなら止めずにマージし、標準出力に `HUMAN_TASKS_PENDING: <件数>` と残りのタスクを出す。この一覧はユーザーに示し、§3「人のタスクの片付け」を案内する。

## 2. ステップ番号

ステップ番号は 3 スキルで共通の通し番号であり、進捗の記録と再開の判定に使う。

| ステップ | 内容 | 担当スキル | チェックポイントの subject |
|---|---|---|---|
| S1 | 準備（`ensure`） | 3 スキル共通 | （コミットなし） |
| S2 | specify（仕様作成） | speckit-feature | `docs(<FEATURE_NAME>): 仕様を作成` |
| S3 | clarify 1 回目 | speckit-feature | `docs(<FEATURE_NAME>): 仕様を明確化（1 回目）` |
| S4 | clarify 2 回目 | speckit-feature | `docs(<FEATURE_NAME>): 仕様を明確化（2 回目）` |
| S5 | plan（詳細設計） | speckit-feature | `docs(<FEATURE_NAME>): 詳細設計を作成` |
| S6 | tasks（タスク分解） | speckit-feature | `docs(<FEATURE_NAME>): タスクを分解` |
| S7-1 | analyze 1 回目 | speckit-feature | `docs(<FEATURE_NAME>): 整合性を検証（1 回目）` |
| S7-2 | analyze 2 回目 | speckit-feature | `docs(<FEATURE_NAME>): 整合性を検証（2 回目）` |
| S7-3 | analyze 3 回目 | speckit-feature | `docs(<FEATURE_NAME>): 整合性を検証（3 回目）` |
| S8 | implement（実装） | speckit-coding | `feat(<FEATURE_NAME>): タスクを実装` |
| S9 | converge（収束） | speckit-coding | `feat(<FEATURE_NAME>): 実装を仕様に収束` |
| S10 | レビュー 1 回目と修正 | speckit-coding | `fix(<FEATURE_NAME>): レビューの指摘を修正（1 回目）` |
| S11 | レビュー 2 回目と修正 | speckit-coding | `fix(<FEATURE_NAME>): レビューの指摘を修正（2 回目）` |
| S12 | 片付け（`finish`） | 3 スキル共通 | `merge(<FEATURE_NAME>): <phase>`（自動。進捗の判定に使うため、この形は変えない） |

`checkpoint` はコミットに trailer `Speckit-Step: <step>` と `Speckit-Feature: <FEATURE_NAME>` を付ける。変更がないステップも空コミットで記録する。進捗は、`main` とブランチにあるこの trailer、`main` にマージ済みの `tasks.md`、`merge(<FEATURE_NAME>): coding|all` のマージコミットから判定する。フィーチャー名付きの trailer はマージの後も残るので、競合を手で解消してマージした後に `finish` を再実行しても進捗は失われない。

`checkpoint` は、機能ファイル（`docs/feature/<FEATURE_NAME>.md`）があれば、その状態欄と `docs/feature/README.md` の一覧の状態列も更新する。S2 で `spec化済み（specs/<FEATURE_NAME>）`、S11 で `完了` にする。S11 の時点で `tasks.md` に未完了の `[人]` のタスクが残っていれば、`完了` ではなく `人の作業待ち（specs/<FEATURE_NAME>）` にする。機能ファイルを手で書き換える必要はない。

## 3. 共通手順

### S1 準備

1. `$HELPER ensure <feature> --phase <phase>` を実行する。`<phase>` は、speckit-feature が `spec`、speckit-coding が `coding`、speckit-all が `all` である。
2. 終了コードが 3 のときは、§1 の表に従って案内し、そのフィーチャーの作業を止める。
3. 出力から `FEATURE_NAME`、`WORKTREE_DIR`、`NEXT_STEP` を控える。
4. `WORKTREE_STATE` が `reused` か `reattached` のときは、`COMPLETED_STEPS` と `NEXT_STEP` をユーザーに示し、`NEXT_STEP` から再開してよいか確認する。ユーザーが別のステップからのやり直しを指示した場合は、そのステップから進める（完了済みの記録は残したまま、成果物を更新する）。
5. `NEXT_STEP` が自分の担当範囲の最後より後（`S12`）なら、本体のステップを飛ばして S12 に進む。

### 各ステップの作業場所

- 以降の作業は、すべて `WORKTREE_DIR` の中で行う。コマンドは `cd "$WORKTREE_DIR"` してから実行し、ファイルは `WORKTREE_DIR` 配下のパスで読み書きする。
- `WORKTREE_DIR/.specify/feature.json` は `ensure` が `specs/<FEATURE_NAME>` を指すように書いている。speckit の各スキルやスクリプトは、この値を対象フィーチャーとして使う。
- 1 つのステップが終わったら、そのステップのチェックポイントを必ず記録する。

  ```bash
  $HELPER checkpoint <FEATURE_NAME> <step> "<§2 の subject>"
  ```

- 長いステップ（特に S8）の途中では、trailer なしの通常のコミットを作ってよい。完了の記録はステップの最後の `checkpoint` だけで行う。

### S12 片付け

1. **worktree の外に出てから**、`$HELPER finish <FEATURE_NAME> --phase <phase>` を実行する（`cd "$REPO_ROOT"`。`REPO_ROOT` は `ensure` の出力にある）。worktree の中で実行すると、スクリプトは止まる。スクリプトは次を行う。
   - 担当範囲の最終ステップ（spec は S7-3、coding と all は S11）が完了していることを確かめる。
   - coding と all では、`tasks.md` に未完了のタスクがないことを確かめる（`[人]` 以外があれば `UNCHECKED_TASKS` で止まる。`[人]` だけなら続けて、最後に `HUMAN_TASKS_PENDING` を出す）。
   - worktree の残りの変更をコミットする。
   - メインの作業ツリーに未コミットの変更がないことを確かめ、`main` に切り替える。
   - `git merge --no-ff -m "merge(<FEATURE_NAME>): <phase>"` でマージする。ブランチがすでにマージ済み（競合を手で解消した後など）なら、マージを飛ばして片付けだけを行う。
   - worktree とブランチを削除する。worktree にあった無視対象のファイル（`.env` など）も一緒に消えるので、出力の `REMOVED_IGNORED` に挙がったものはユーザーに知らせる。
2. マージで競合したときは、worktree とブランチが残る。競合の内容をユーザーに示し、解消方針を確認してから、メインの作業ツリーで解消してマージをコミットし、もう一度 `finish` を実行する。マージコミットのメッセージは `merge(<FEATURE_NAME>): <phase>` のままにする。

### 人のタスクの片付け

`[人]` のタスクは、マージの後に `main` で片付けてよい。規則はプロジェクトの steering（「人が行うタスク」）に従う。

1. `$HELPER human-tasks <FEATURE_NAME>` で残りを示す。
2. ユーザーが完了を伝えたら、そのタスクの「完了の確かめ方」で確かめられる部分を確かめ、`main` の `tasks.md` を `- [x]` にする。
3. `$HELPER sync-status <FEATURE_NAME>` で状態欄を合わせる。人のタスクがなくなれば `完了` になる。
4. `tasks.md` と機能ファイル、`docs/feature/README.md` の変更をまとめてコミットする（例: `docs(<FEATURE_NAME>): 人のタスクの完了を記録`）。

### 中止

`$HELPER abort <FEATURE_NAME>` で削除対象を表示し、ユーザーの明示的な同意を得てから `--yes` を付けて実行する。ユーザーの指示なしに中止してはならない。

## 4. 共通規則

- **対話的な確認**: 仕様の曖昧さ、設計判断、実装方針の分岐、レビュー指摘の修正方針など、ユーザーの判断が必要な事項は、推奨案（`**Recommended:**`）を添えて質問し、合意を得てから進める。引数に `--auto` があるときは、質問せずに §6 の自動モードで進める（各スキル本文の 💬 の質問と、標準スキルの確認も含む）。
- **破壊的コマンドの禁止**: `rm -rf`、`git reset --hard`、`git clean -f`、`git push --force` などの破壊的コマンドは使わない。worktree とブランチの操作は `$HELPER` だけで行う。
- **言語**: 応答と成果物は、プロジェクトの言語ルール（`.kiro/steering/language.md` など）に従う。ルールがない場合も日本語で書く。
- **テスト・ビルド・リンター**: 実行するコマンドは、`plan.md` の技術コンテキスト、`quickstart.md`、プロジェクトの設定ファイル（`package.json`、`Makefile`、`pyproject.toml` など）から判断する。判断できない場合はユーザーに確認する。
- **コマンドの書き方**: speckit のスキル本文にある `$speckit-plan` のようなコマンド参照は、実行中のエージェントの呼び出し方に読み替える。

## 5. 引数の解釈と複数フィーチャーの進め方

| 指定 | 例 | 動作 |
|---|---|---|
| 単一 | `1`、`002`、`002-auth`、`auth` | `$HELPER resolve` で 1 件に決める |
| 範囲 | `002-005`、`002..005` | `$HELPER list` の結果から番号が範囲内のものを番号順に選ぶ |
| 全件 | `all` | `$HELPER next --phase <phase>` を、空になるまで繰り返す |
| なし | （空） | `$HELPER next --phase <phase>` の 1 件。空なら対象なしと報告する |
| 自動モード | `--auto`、`002-005 --auto`、`--auto all` | 上のいずれかと組み合わせる。質問せずに推奨案を採用して進める（§6） |

- `--auto` は位置を問わない。フィーチャーの指定を解釈する前に取り除き、`$HELPER` には渡さない。
- 一覧にない新しいフィーチャーは、`001-short-name` の形の完全名で指定する。
- 複数のフィーチャーは 1 件ずつ直列に進める。前のフィーチャーの S12（マージ）が終わってから、次のフィーチャーの S1 に進む。後続のフィーチャーは、先行フィーチャーの成果を含む最新の `main` から分岐する。
- 範囲指定の途中で `ALREADY_SPECIFIED` や `ALREADY_IMPLEMENTED` になったフィーチャーは、飛ばしたことを記録して次に進む。それ以外の理由で止まったときは、飛ばして続けるか中断するかをユーザーに確認する（自動モードでは確認せずに飛ばす。§6「止まったときの扱い」）。
- `all` で飛ばしたフィーチャーは、以降の `next` に `--skip <飛ばしたもの,...>` を付けて除く（付けないと、途中の worktree が残っているフィーチャーがまた選ばれる）。

## 6. 自動モード（`--auto`）

引数に `--auto` があるときは、ユーザーに質問せず、エージェント自身が示す推奨案を採用して進める。範囲指定や `all` と組み合わせて、無人で続けて流す使い方を想定する。

仕様駆動開発の「曖昧さを推測で埋めない」に反しないよう、自動で決めたことはすべて推奨案として明示し、後から見直せる形で記録する（下の「記録」）。安全規則（§4 の破壊的コマンドの禁止など）は、自動モードでも変わらない。

### 推奨案を自動で採用する場面

| 場面 | 自動モードでの動作 |
|---|---|
| S1 の再開確認（`WORKTREE_STATE` が `reused` / `reattached`） | `NEXT_STEP` から再開する |
| S2〜S4 の前提条件・スコープの疑問、clarify の質問 | 推奨案（`**Recommended:**`）を回答として採用する。推奨案を 1 つに絞れない論点は、範囲が狭く後から広げやすい選択肢を採る |
| S5 のアーキテクチャのトレードオフ、ライブラリの選定 | 推奨案を採用し、`research.md` に Decision・Rationale・Alternatives considered を残す。`docs/architecture.md` と `docs/nfr.md` から外れる選択はしない |
| S7 の修正方針、`speckit-analyze` の「修正案を示しますか」 | 「はい」とみなし、推奨の修正を当てる |
| S8 の `speckit-implement` の「チェックリストに未完了の項目があるが続けるか」 | 続行する。未完了の項目を完了報告に挙げる |
| S8〜S11 の実装方針の分岐、ギャップの解消方針、レビュー指摘の対応方針 | 推奨案を採用する。仕様を変える場合は、コードだけでなく `spec.md`、`plan.md`、`tasks.md` にも反映する |
| `LEFTOVER_CHANGES` | worktree の変更はこのフィーチャーの作業で生じたものなので、`--commit-leftovers` を付けて `finish` を再実行する。含めた変更の一覧を完了報告に挙げる |
| `UNCHECKED_TASKS` | 未完了のタスクを S8 の手順で実装し、テストが通ったら `finish` を再実行する（`--allow-unchecked` は自動で付けない） |
| S8 の `[人]` のタスク | 実行せず、`[x]` にもしない。手順を示して保留にし、依存しない後続のタスクを続ける。保留にしたタスクを完了報告に挙げる |
| `HUMAN_TASKS_PENDING` | マージは済んでいる。残りの `[人]` のタスクを完了報告に挙げる（自動で完了にしない） |

### 自動モードでも止まる場面

次の場面は、推奨案を選んでも取り返しがつかないか、推測で進めると危険なので、自動では進めない。

- `finish` でのマージの競合（自動で解消しない）
- 中止（`abort`）。ユーザーの明示的な同意が必要である
- `NOT_ON_MAIN`（メインの作業ツリーのブランチを自動で切り替えない）
- `UNCHECKED_TASKS` で、未完了のタスクを実装しても残る場合
- テスト・ビルド・リンターのコマンドが §4 の情報源から判断できない場合
- テストやビルドの失敗が、同じ原因に対して 3 回直しても解消しない場合
- S2 で、機能概要も追加指示もなく、何を作るかが決められない場合
- 憲章、`docs/architecture.md`、`docs/nfr.md` の変更が必要になった場合（これらの改訂は自動で行わない）

### 止まったときの扱い

1. worktree とブランチはそのまま残し、止まった理由、止まったステップ、ユーザーに判断してほしい事項（選択肢と推奨案）を記録する。
2. 単一のフィーチャーの指定なら、完了報告を出して終了する。
3. 範囲指定や `all` なら、そのフィーチャーを飛ばして次に進む（`all` では `next` の `--skip` に加える）。後続のフィーチャーの機能概要の `**依存**` に、飛ばしたフィーチャーが含まれる場合は、そのフィーチャーも飛ばす。
4. 止まったフィーチャーは、ユーザーが判断した後に、同じスキルをもう一度実行すれば（`--auto` の有無を問わない）続きのステップから再開できる。

### 記録

- **clarify（S3、S4）**: 見出しを `### Session YYYY-MM-DD (Round 1, auto)` のようにし、自動で採用した回答の行末に `(auto)` を付ける。
- **自動判断の一覧**: 自動で採用したすべての判断を `FEATURE_DIR/auto-decisions.md` に追記する。1 件ごとにステップ、論点、選択肢、採用した案、理由、反映したファイルを書く。clarify の回答もここに併記する。
- **完了報告**: 各スキルの完了報告に、`auto-decisions.md` の要約（見直しを勧める判断を先に）と、止まったフィーチャーとその理由、ユーザーに判断してほしい事項を加える。見直すときは `speckit-clarify` や該当するスキルを案内する。

## 7. 手動での利用

ユーザーからこのスキルを直接呼ばれたときは、引数に応じて次を行う。

- `status`（または引数なし）: `$HELPER status` の結果を表示し、途中の worktree があれば再開に使うスキルを案内する。人の作業が残っているフィーチャーがあれば、`human-tasks` での確認を案内する。
- `human-tasks [<feature>]`: 結果を表示する。
- `sync-status <feature>`: §3「人のタスクの片付け」の手順に従う。
- `next --phase <phase>`: 結果を表示する。
- `abort <feature>`: §3「中止」の手順に従う。

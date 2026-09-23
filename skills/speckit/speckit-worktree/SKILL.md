---
name: "speckit-worktree"
description: "speckit-feature・speckit-coding・speckit-all が共通で使う worktree 管理スキル。フィーチャーごとの Git worktree とブランチの準備（既存があれば再利用）、ステップ完了ごとの進捗コミット、main への --no-ff マージと片付け、中止、進捗の確認を行う。3 スキル共通の実行規則（ステップ番号、再開、安全規則、対話、引数の解釈）もここに定める。「フィーチャーの進捗を見せて」「worktree を破棄して」と言われたとき、または /speckit-worktree と打たれたときにも使う。"
argument-hint: "status | next --phase spec|coding|all | abort <フィーチャー>"
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
| `$HELPER finish <feature> --phase spec\|coding\|all [--allow-unchecked]` | S12 片付け。`main` に `--no-ff` でマージし、worktree とブランチを削除する。worktree の外で実行する |
| `$HELPER abort <feature> [--yes]` | worktree とブランチを破棄する。`--yes` がなければ対象を表示するだけ |
| `$HELPER list` | 全フィーチャー名を着手順（`spec_order.md` の並び、その後に番号順）で表示する |
| `$HELPER status` | 全フィーチャーの仕様・実装・worktree の状況を表示する |
| `$HELPER next --phase spec\|coding\|all` | 次に着手すべきフィーチャーを表示する（途中の worktree を優先） |
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
| `UNCHECKED_TASKS` | `finish`（coding / all）で、`tasks.md` に未完了のタスクが残っている | 未完了のタスクの一覧をユーザーに示す。実装するなら S8 の手順で片付けてから、残したままマージしてよいと確認できたら `--allow-unchecked` を付けて `finish` を再実行する |

## 2. ステップ番号

ステップ番号は 3 スキルで共通の通し番号であり、進捗の記録と再開の判定に使う。

| ステップ | 内容 | 担当スキル | チェックポイントの subject |
|---|---|---|---|
| S1 | 準備（`ensure`） | 3 スキル共通 | （コミットなし） |
| S2 | specify（仕様作成） | speckit-feature | `docs(spec): specify <FEATURE_NAME>` |
| S3 | clarify 1 回目 | speckit-feature | `docs(spec): clarify round 1 <FEATURE_NAME>` |
| S4 | clarify 2 回目 | speckit-feature | `docs(spec): clarify round 2 <FEATURE_NAME>` |
| S5 | plan（詳細設計） | speckit-feature | `docs(plan): plan <FEATURE_NAME>` |
| S6 | tasks（タスク分解） | speckit-feature | `docs(tasks): tasks <FEATURE_NAME>` |
| S7-1 | analyze 1 回目 | speckit-feature | `docs(spec): analyze pass 1 <FEATURE_NAME>` |
| S7-2 | analyze 2 回目 | speckit-feature | `docs(spec): analyze pass 2 <FEATURE_NAME>` |
| S7-3 | analyze 3 回目 | speckit-feature | `docs(spec): analyze pass 3 <FEATURE_NAME>` |
| S8 | implement（実装） | speckit-coding | `feat(<FEATURE_NAME>): implement tasks` |
| S9 | converge（収束） | speckit-coding | `feat(<FEATURE_NAME>): converge implementation` |
| S10 | レビュー 1 回目と修正 | speckit-coding | `fix(<FEATURE_NAME>): address review feedback (round 1)` |
| S11 | レビュー 2 回目と修正 | speckit-coding | `fix(<FEATURE_NAME>): address review feedback (round 2)` |
| S12 | 片付け（`finish`） | 3 スキル共通 | `merge(<FEATURE_NAME>): <phase>`（自動） |

`checkpoint` はコミットに trailer `Speckit-Step: <step>` と `Speckit-Feature: <FEATURE_NAME>` を付ける。変更がないステップも空コミットで記録する。進捗は、`main` とブランチにあるこの trailer、`main` にマージ済みの `tasks.md`、`merge(<FEATURE_NAME>): coding|all` のマージコミットから判定する。フィーチャー名付きの trailer はマージの後も残るので、競合を手で解消してマージした後に `finish` を再実行しても進捗は失われない。

`checkpoint` は、機能ファイル（`docs/feature/<FEATURE_NAME>.md`）があれば、その状態欄と `docs/feature/README.md` の一覧の状態列も更新する。S2 で `spec化済み（specs/<FEATURE_NAME>）`、S11 で `完了` にする。機能ファイルを手で書き換える必要はない。

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
   - coding と all では、`tasks.md` に未完了のタスクがないことを確かめる（あれば `UNCHECKED_TASKS` で止まる）。
   - worktree の残りの変更をコミットする。
   - メインの作業ツリーに未コミットの変更がないことを確かめ、`main` に切り替える。
   - `git merge --no-ff -m "merge(<FEATURE_NAME>): <phase>"` でマージする。ブランチがすでにマージ済み（競合を手で解消した後など）なら、マージを飛ばして片付けだけを行う。
   - worktree とブランチを削除する。
2. マージで競合したときは、worktree とブランチが残る。競合の内容をユーザーに示し、解消方針を確認してから、メインの作業ツリーで解消してマージをコミットし、もう一度 `finish` を実行する。マージコミットのメッセージは `merge(<FEATURE_NAME>): <phase>` のままにする。

### 中止

`$HELPER abort <FEATURE_NAME>` で削除対象を表示し、ユーザーの明示的な同意を得てから `--yes` を付けて実行する。ユーザーの指示なしに中止してはならない。

## 4. 共通規則

- **対話的な確認**: 仕様の曖昧さ、設計判断、実装方針の分岐、レビュー指摘の修正方針など、ユーザーの判断が必要な事項は、推奨案（`**Recommended:**`）を添えて質問し、合意を得てから進める。
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

- 一覧にない新しいフィーチャーは、`001-short-name` の形の完全名で指定する。
- 複数のフィーチャーは 1 件ずつ直列に進める。前のフィーチャーの S12（マージ）が終わってから、次のフィーチャーの S1 に進む。後続のフィーチャーは、先行フィーチャーの成果を含む最新の `main` から分岐する。
- 範囲指定の途中で `ALREADY_SPECIFIED` や `ALREADY_IMPLEMENTED` になったフィーチャーは、飛ばしたことを記録して次に進む。それ以外の理由で止まったときは、飛ばして続けるか中断するかをユーザーに確認する。

## 6. 手動での利用

ユーザーからこのスキルを直接呼ばれたときは、引数に応じて次を行う。

- `status`（または引数なし）: `$HELPER status` の結果を表示し、途中の worktree があれば再開に使うスキルを案内する。
- `next --phase <phase>`: 結果を表示する。
- `abort <feature>`: §3「中止」の手順に従う。

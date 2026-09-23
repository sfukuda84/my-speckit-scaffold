---
inclusion: always
---

# 仕様駆動開発ルール（Spec Kit）

このプロジェクトは [GitHub Spec Kit](https://github.com/github/spec-kit) による **仕様駆動開発（Spec-Driven Development）** で進める。コードは仕様から導くものであり、仕様を経ずに機能を実装しない。

## 基本原則

1. **仕様が先、コードが後**: 新機能や振る舞いの変更は、必ず `spec.md` → `plan.md` → `tasks.md` の順に成果物を作ってから実装する。
2. **憲章（constitution）が最上位**: `.specify/memory/constitution.md` をすべての判断の基準とする。計画や実装が憲章と矛盾する場合は、先に憲章との整合を取る。
3. **仕様は「何を・なぜ」、計画は「どう作るか」**: `spec.md` には技術スタックや実装詳細を書かず、ユーザー価値と要件に集中する。技術的な選択は `plan.md` に書く。
4. **曖昧さは推測で埋めない**: 不明点は `[NEEDS CLARIFICATION: ...]` として明示し、`/speckit-clarify` やユーザーへの確認で解消する。
5. **成果物と実装を同期させる**: 実装中に仕様の誤りや不足が見つかったら、コードだけを直さず `spec.md` / `plan.md` / `tasks.md` にも反映する。
6. **アーキテクチャと非機能要件に従う**: 各機能の `plan.md` は `docs/architecture.md`（構成と技術スタック）と `docs/nfr.md`（全機能が守る非機能要件）に従う。これらと違う技術や目標が必要になった場合は、`plan.md` で独自に決めず、`speckit-architecture` や `speckit-nfr-feature` の更新モードで先に見直す。

## 標準ワークフロー

| 手順 | コマンド | 成果物 | 目的 |
|---|---|---|---|
| 0 | `speckit-constitution` | `.specify/memory/constitution.md` | プロジェクトの原則を定める（初回と改訂時） |
| 1 | `speckit-specify` | `specs/<NNN-name>/spec.md` | 自然言語の要求から仕様を作る |
| 2 | `speckit-clarify` | `spec.md`（更新） | 曖昧な点を質問して仕様に反映する（推奨） |
| 3 | `speckit-plan` | `plan.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md` | 技術的な設計と実装計画を作る |
| 4 | `speckit-checklist` | `checklists/*.md` | 要件の品質を確認するチェックリストを作る（任意） |
| 5 | `speckit-tasks` | `tasks.md` | 依存順に並べた実装タスクを作る |
| 6 | `speckit-analyze` | 分析レポート（非破壊） | spec / plan / tasks の整合性を検査する（推奨） |
| 7 | `speckit-implement` | ソースコード、`tasks.md`（進捗更新） | タスクに従って実装する |
| 8 | `speckit-converge` | `tasks.md`（追記） | 実装と仕様の差分を洗い出し、残作業をタスクに加える |
| - | `speckit-taskstoissues` | GitHub Issues | タスクを Issue に変換する（任意） |

コマンドの呼び出し方はエージェントごとに異なる。

| エージェント | コマンド定義の場所 | 呼び出し例 |
|---|---|---|
| Claude Code | `.claude/skills/speckit-*/` | `/speckit-specify <要求>` |
| Codex CLI | `.agents/skills/speckit-*/` | `$speckit-specify <要求>` |
| Antigravity (agy) | `.agents/skills/speckit-*/` | スキル `speckit-specify` を指定して依頼する |
| Kiro CLI | `.kiro/skills/speckit-*/` | スキル `speckit-specify` を指定して依頼する |
| opencode | `.opencode/commands/speckit.*.md` | `/speckit.specify <要求>` |

`.claude/skills/`、`.agents/skills/`、`.kiro/skills/` の各 `speckit-*` は、プロジェクト内の共有スキル `skills/speckit/` への相対シンボリックリンクであり、全エージェントが同じスキル定義を使う。

共有スキルは Codex 向けに生成されているため、スキル本文中のコマンド参照は `$speckit-plan` のような Codex の書き方になっている。ユーザーに次のコマンドを提示するときは、上の表に従って自分のエージェントの呼び出し方に読み替える（例: Claude Code と Antigravity では `/speckit-plan`、Kiro CLI ではスキル名 `speckit-plan`、opencode では `/speckit.plan`）。

### 追加スキル

新規プロジェクトの立ち上げでは、`speckit-bootstrap` が次の順にスキルを実行する: `speckit-concept-2-feature` → `speckit-architecture` → `speckit-constitution` → `speckit-common-feature` → `speckit-nfr-feature` → 検証。

| スキル | 目的 |
|---|---|
| `speckit-bootstrap` | 新規プロジェクトの立ち上げ（上の順）を通しで行う。ステップごとにコミットし、中断しても続きから再開できる |
| `speckit-architecture` | 機能一覧を実現するアーキテクチャと技術スタックを、SaaS/PaaS・クラウド・VPS の 3 系統の比較から選び、`docs/architecture.md` に書く |
| `speckit-common-feature` | 認証やメール送信など、コアドメイン以外の共通機能を `docs/feature/000-app-basic.md` に定義する |
| `speckit-nfr-feature` | 全機能が守る非機能要件を `docs/nfr.md` に、監視・バックアップ・CI/CD などの運用基盤を `docs/feature/999-app-nfr.md` に定義する |
| `speckit-project` | 市場規模、価格と収支計画、KPI、スケジュール、体制、リスクをヒアリングと出典付きの調査で決め、事業計画の正本 `docs/project.md` に書く。収支は `plan.py` で計算する（立ち上げの後に任意で実行する） |
| `speckit-presentation` | `docs/project.md` などの成果物から、読み手（社内の承認・投資家・顧客）に合わせた企画書を `docs/presentation/<読み手>/` に作る。内容は `slides.md`、見た目は `design.yaml` に書き、`build_pptx.py` で pptx にする（pptx は手で直さない） |
| `speckit-concept-2-feature` | `docs/concept/` のコアコンセプトを、`speckit-specify` に渡せる単位の機能概要（`docs/feature/`）と着手順序（`spec_order.md`）に仕分ける |
| `speckit-feature` | 仕様工程。worktree で specify・clarify ×2・plan・tasks・analyze ×3 を行い、`main` にマージする |
| `speckit-coding` | 実装工程。worktree で implement・converge・レビュー ×2 を行い、`main` にマージする |
| `speckit-all` | `speckit-feature` と `speckit-coding` を 1 つの worktree で通して行い、最後に `main` にマージする |
| `speckit-worktree` | 上の 3 スキルが使う worktree 管理と共通の実行規則。進捗の確認（`status`）や中止（`abort`）にも使う |
| `speckit-review` | Standards 軸と Spec 軸の 2 軸でコード変更をレビューする |

`speckit-feature`、`speckit-coding`、`speckit-all` は、フィーチャーごとに `.worktrees/<NNN-name>`（ブランチ `feature/<NNN-name>`）で作業し、ステップごとにコミットして進捗を記録する。中断しても、どのスキルからでも続きのステップから再開できる。

## エージェントの行動規範

- ユーザーが機能追加や変更を依頼し、対応する `specs/` のフィーチャーがまだない場合は、いきなり実装せず、まず `speckit-specify` から始めることを提案する。
- 各コマンドは前の手順の成果物を前提とする。前提の成果物がない場合は、欠けている手順を案内する。
- `tasks.md` の完了したタスクは `- [x]` に更新し、進捗と実態を一致させる。
- 1 つの手順が終わったら結果を要約し、次に実行すべきコマンドを提示する。
- 誤字修正、依存関係の更新、設定の微調整など、振る舞いを変えない軽微な変更は仕様化を省略してよい。判断に迷ったらユーザーに確認する。
- Spec Kit とスキルのスクリプトは Python（3.9 以上）で書かれており、`python3 <スクリプト>` の形で呼ぶ。`python3` というコマンドがない環境（Windows など）では、`python` または `py -3` に読み替えて実行する。

## ディレクトリ構成

```text
.specify/
├── memory/constitution.md   # プロジェクト憲章（最上位の規範）
├── templates/               # spec / plan / tasks などのテンプレート
├── scripts/python/          # Spec Kit のヘルパースクリプト（Python）
└── workflows/               # Spec Kit のワークフロー定義
specs/
└── <NNN-feature-name>/      # フィーチャーごとの成果物
    ├── spec.md
    ├── plan.md
    ├── research.md
    ├── data-model.md
    ├── quickstart.md
    ├── contracts/
    ├── checklists/
    └── tasks.md
docs/
├── concept/                 # コアコンセプト（入力）と backlog.md
├── feature/                 # 機能概要（000 は共通基盤、999 は運用基盤）と spec_order.md
├── architecture.md          # 構成と技術スタック（speckit-architecture）
├── project.md               # 事業計画（speckit-project）
├── presentation/            # 企画書（speckit-presentation）。design.yaml と <読み手>/slides.md・proposal.pptx
└── nfr.md                   # 全機能が守る非機能要件（speckit-nfr-feature）
.kiro/steering/              # エージェント共通ルールの正本（このディレクトリ）
```

`.specify/templates/`、`.specify/scripts/`、各エージェントの `speckit-*` スキルは Specify CLI が管理するファイルなので、直接編集しない。

このプロジェクトでは `specify init --here --force`、`specify integration install` / `upgrade` / `switch` / `uninstall` を実行しない。スキルがシンボリックリンクのため、リンク先の共有スキルがエージェント固有の内容で上書きされるか、削除される。エージェント向けの manifest（`.specify/integrations/*.manifest.json`）は実体と対応しないため置いていない。スキルを更新するときは、`skills/speckit/` 側で行う。

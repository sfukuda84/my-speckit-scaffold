# my-speckit-scaffold

[GitHub Spec Kit](https://github.com/github/spec-kit) による仕様駆動開発（Spec-Driven Development）を、複数の AI エージェントで同じ手順で進めるためのプロジェクト scaffold。

> **使い方は [MANUAL.md](MANUAL.md)（利用マニュアル）にまとめている。** 最小の手順、事業計画と企画書の作り方、企画書のテンプレートの差し替え方法などは、そちらを見る。この README は、仕組みと scaffold の開発者向けの説明である。

- 次の 5 つのエージェントで、同じ Spec Kit のスキルとルールを使う。
  - Claude Code
  - Codex CLI
  - Antigravity（agy）
  - Kiro CLI
  - opencode
- エージェント向けのルールは `.kiro/steering/` だけで管理する。`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`opencode.json` は、そこを参照するだけである。
- スキルの本体は `skills/speckit/` に 1 セットだけ置き、各エージェントのスキルディレクトリからシンボリックリンクで参照する。
- `new-speckit-project` コマンドで新規プロジェクトを作ると、コアコンセプトから機能一覧、アーキテクチャ、憲章、共通基盤、非機能要件までを、エージェントとの対話で作れる。
- 仕様工程と実装工程を Git worktree で分けて実行し、途中で中断しても続きから再開できる。
- スクリプトはすべて Python（標準ライブラリのみ）で書かれており、macOS、Linux、Windows で動く。

## 必要なもの

- Git
- Python 3.9 以上
- [uv](https://docs.astral.sh/uv/)（`new-speckit-project` の導入に使う）
- 使うエージェントの CLI（1 つ以上）
- scaffold を更新する場合のみ: [Specify CLI](https://github.com/github/spec-kit)（`specify`）。このプロジェクトは 1.0.10 で生成した。

## 新しいプロジェクトを始める

### 1. コマンドを入れる（初回だけ）

```bash
uv tool install "git+https://github.com/sfukuda84/my-speckit-scaffold#subdirectory=tool"
```

更新は `uv tool upgrade new-speckit-project` で行う。

### 2. プロジェクトを作る

```bash
new-speckit-project ~/work/my-app                      # コアコンセプトを対話で入力する
new-speckit-project ~/work/my-app -m "コアコンセプト"   # 入力を省く
new-speckit-project ~/work/my-app --agent codex        # 使うエージェントを選ぶ（既定は claude）
```

コマンドは次を行う。

1. scaffold を GitHub から clone し、`tool/` と scaffold の履歴を取り除く（`--ref` でブランチやタグを指定できる）。
2. スキルのシンボリックリンクを確かめる。リンクを作れない環境（Windows で開発者モードがオフなど）では、スキルの実体のコピーに切り替えて警告する。
3. コアコンセプトを `docs/concept/core-concept.md` に保存し、`git init` と初回コミットを行う。scaffold の README は `docs/speckit-scaffold.md` に移る。
4. 指定のエージェントを対話モードで起動し、`speckit-bootstrap` を始める。

オプションの一覧は [tool/README.md](tool/README.md) を参照する。

作成済みのプロジェクトに scaffold の新しい版を取り込むときは、プロジェクトの `main` で `new-speckit-project update` を実行する（手で直したファイルは上書きせず、新しい版を `.scaffold-new/` に置く。詳しくは [MANUAL.md](MANUAL.md) の §9）。

### 3. 立ち上げ（speckit-bootstrap）

エージェントとの対話で、次の順に作る。各ステップが終わるとコミットされ、中断しても `speckit-bootstrap` を再実行すれば続きから再開できる。

| ステップ | スキル | 成果物 |
|---|---|---|
| B1 | `speckit-concept-2-feature` | `docs/feature/`（機能概要 `001-*.md` 以降、`spec_order.md`、`premises.md`） |
| B2 | `speckit-architecture` | `docs/architecture.md`（SaaS/PaaS・クラウド・VPS の 3 系統を比べて選んだ構成と技術スタック） |
| B3 | `speckit-constitution` | `.specify/memory/constitution.md` |
| B4 | `speckit-common-feature` | `docs/feature/000-app-basic.md`（認証、メール送信などの共通基盤） |
| B5 | `speckit-nfr-feature` | `docs/nfr.md`（全機能が守る非機能要件）と `docs/feature/999-app-nfr.md`（監視、バックアップ、CI/CD などの運用基盤） |
| B6 | （検証） | 機能一式の整合の確認 |

### 4. 仕様化と実装

`speckit-all` を引数なしで実行すると、`000-app-basic` から 1 件ずつ、仕様から実装までを通して進める。工程を分けたい場合は `speckit-feature`（仕様）と `speckit-coding`（実装）を使う（→「worktree を使った実行」）。

### 5. 事業計画（任意）

事業計画（市場規模、価格と収支計画、KPI、スケジュール、体制、リスク）が必要な場合は、`speckit-project` で `docs/project.md` を作る。収支は、前提の表から `plan.py` が楽観・標準・悲観の 3 シナリオで計算する。

### 6. 企画書（任意）

`speckit-presentation` で、成果物から読み手（社内の承認 `internal`、投資家 `investor`、顧客・パートナー `customer`）に合わせた企画書を PowerPoint で作る。

- 内容は `docs/presentation/<読み手>/slides.md`、見た目は `docs/presentation/design.yaml` に書き、`build_pptx.py`（`uv run` で実行。python-pptx を使う）が `proposal.pptx` にする。
- 会社の雛形の .pptx を `design.yaml` の `template` に指定すると、その背景とマスターの上に描く。
- pptx を PowerPoint で手で直すと、次に作り直したときに消える。直したい点は `slides.md` か `design.yaml` に反映する。
- 数字は成果物（とくに `docs/project.md`）にあるものだけを使い、出典をスライドに入れる。

## ディレクトリ構成

```text
.
├── README.md
├── CLAUDE.md                 # Claude Code 用。.kiro/steering を @import する
├── GEMINI.md                 # Antigravity / Gemini 用。.kiro/steering を @import する
├── AGENTS.md                 # Codex CLI など用。.kiro/steering を読むよう指示する
├── opencode.json             # opencode 用。instructions で .kiro/steering/*.md を読み込む
├── .kiro/
│   ├── steering/             # エージェント共通ルールの正本
│   │   ├── language.md       #   応答と成果物は日本語
│   │   └── spec-driven-development.md  # Spec Kit による仕様駆動開発のルール
│   └── skills/               # → skills/speckit/* へのシンボリックリンク（Kiro CLI）
├── .claude/skills/           # → skills/speckit/* へのシンボリックリンク（Claude Code）
├── .agents/skills/           # → skills/speckit/* へのシンボリックリンク（Codex CLI / Antigravity）
├── .opencode/commands/       # opencode 用の Spec Kit コマンド（Specify CLI が生成）
├── .specify/                 # Spec Kit の憲章、テンプレート、Python スクリプト（Specify CLI が生成）
├── skills/speckit/           # 共有スキルの本体
├── docs/
│   ├── concept/              # コアコンセプト（入力）と backlog.md
│   ├── feature/              # 機能概要と着手順序
│   ├── architecture.md       # 構成と技術スタック（speckit-architecture が作る）
│   ├── project.md            # 事業計画（speckit-project が作る）
│   ├── presentation/         # 企画書（speckit-presentation が作る）
│   └── nfr.md                # 非機能要件（speckit-nfr-feature が作る）
├── specs/                    # フィーチャーごとの仕様・設計・タスク（Spec Kit の成果物）
├── .github/workflows/        # scaffold 自体のテスト（新規プロジェクトには含まれない）
└── tool/                     # new-speckit-project コマンドとテスト（新規プロジェクトには含まれない）
```

## ルールの管理

エージェント向けのルールは `.kiro/steering/` のファイルにだけ書く。`CLAUDE.md` などに直接書くと、二重に管理することになる。

| ファイル | 読み込み方 |
|---|---|
| `CLAUDE.md` | `@.kiro/steering/*.md` の import |
| `GEMINI.md` | `@.kiro/steering/*.md` の import と、読み込むよう求める本文 |
| `AGENTS.md` | steering のファイル一覧と、読み込むよう求める本文 |
| `opencode.json` | `"instructions": [".kiro/steering/*.md"]` |
| Kiro CLI | `.kiro/steering/` を直接読む（`inclusion: always`） |

steering のファイルを追加したときは、`CLAUDE.md`、`GEMINI.md`、`AGENTS.md` の参照リストにも 1 行ずつ足す。`opencode.json` は glob で読むので変更は要らない。

## スキル

### Spec Kit の標準スキル

| 手順 | スキル | 成果物 |
|---|---|---|
| 0 | `speckit-constitution` | `.specify/memory/constitution.md` |
| 1 | `speckit-specify` | `specs/<NNN-name>/spec.md` |
| 2 | `speckit-clarify` | `spec.md`（更新） |
| 3 | `speckit-plan` | `plan.md`、`research.md`、`data-model.md`、`contracts/`、`quickstart.md` |
| 4 | `speckit-checklist` | `checklists/*.md` |
| 5 | `speckit-tasks` | `tasks.md` |
| 6 | `speckit-analyze` | 整合性の分析レポート |
| 7 | `speckit-implement` | ソースコード、`tasks.md`（進捗） |
| 8 | `speckit-converge` | `tasks.md`（残作業の追記） |
| - | `speckit-taskstoissues` | GitHub Issues |

### 追加スキル

| スキル | 内容 |
|---|---|
| `speckit-bootstrap` | 新規プロジェクトの立ち上げ（B1〜B6）を通しで行う |
| `speckit-concept-2-feature` | `docs/concept/` を、`speckit-specify` に 1 回で渡せる単位の機能概要（`docs/feature/`）に仕分ける。共通機能は機能にせず、共通基盤の候補として記録する |
| `speckit-architecture` | 機能一覧を実現する構成と技術スタックを、3 系統の比較から選んで `docs/architecture.md` に書く |
| `speckit-common-feature` | 認証やメール送信などの共通機能を `docs/feature/000-app-basic.md` に定義する |
| `speckit-project` | 事業計画（市場、価格と収支、KPI、スケジュール、体制、リスク）を `docs/project.md` に定義する。収支は `plan.py` で計算・検算する |
| `speckit-presentation` | 成果物から、読み手に合わせた企画書（pptx）を作る。内容は `slides.md`、見た目は `design.yaml`、変換は `build_pptx.py` |
| `speckit-nfr-feature` | 非機能要件を `docs/nfr.md`（横断要件）と `docs/feature/999-app-nfr.md`（運用基盤）に定義する |
| `speckit-feature` | 仕様工程。specify → clarify ×2 → plan → tasks → analyze ×3 を行い、`main` にマージする |
| `speckit-coding` | 実装工程。implement → converge → レビュー ×2 を行い、`main` にマージする |
| `speckit-all` | 仕様工程と実装工程を 1 つの worktree で通して行い、最後に `main` にマージする |
| `speckit-worktree` | 上の 3 スキルが使う worktree の管理と、共通の実行規則。進捗の確認（`status`）や中止（`abort`）にも使う |
| `speckit-review` | Standards 軸と Spec 軸の 2 軸でコード変更をレビューする |

機能の番号のうち、`000` は共通基盤、`999` は運用基盤の予約番号である。コアドメインの機能は `001` から振る。

### スキルの呼び出し方

| エージェント | 例 |
|---|---|
| Claude Code | `/speckit-all 001` |
| Codex CLI | `$speckit-all 001` |
| Antigravity | `/speckit-all 001` |
| Kiro CLI | 「`speckit-all` スキルで 001 を進めて」と依頼する |
| opencode | Spec Kit の標準コマンドは `/speckit.specify` など。追加スキルは「`speckit-all` スキルで…」と依頼する |

共有スキルは Codex 向けに生成されたものなので、本文中のコマンド参照は `$speckit-plan` のように書かれている。steering に読み替えのルールがあるので、各エージェントは自分の書き方で次のコマンドを案内する。

## worktree を使った実行（speckit-feature / speckit-coding / speckit-all）

フィーチャーごとに `.worktrees/<NNN-name>`（ブランチ `feature/<NNN-name>`）で作業し、ステップが終わるたびにコミットする。コミットには trailer `Speckit-Step: <ステップ>` と `Speckit-Feature: <NNN-name>` を付けて進捗を記録する。着手順は `docs/feature/spec_order.md` の並びに従い、機能ファイルの状態欄は S2 で `spec化済み`、S11 で `完了` に自動で更新される。

| ステップ | 内容 | 担当 |
|---|---|---|
| S1 | 準備。worktree があれば再利用し、なければ `main` から作る | 3 スキル共通 |
| S2〜S7-3 | specify、clarify ×2、plan、tasks、analyze ×3 | speckit-feature |
| S8〜S11 | implement、converge、レビュー ×2 | speckit-coding |
| S12 | `main` への `--no-ff` マージと、worktree・ブランチの削除 | 3 スキル共通 |

- **単独で実行したとき**: `speckit-feature` と `speckit-coding` は、それぞれ自分の工程の最後に `main` へマージする。`speckit-coding` は、マージ済みの `main` から新しく worktree を作る。
- **`speckit-all` のとき**: 仕様工程の後もマージせず、同じ worktree のまま実装工程に進む。
- **中断したとき**: worktree が残っていれば、どのスキルからでも続きのステップから再開できる。エージェントを変えて再開してもよい。
- **引数**: 番号（`1`、`002`）、範囲（`002-005`）、`all`、省略（次の未着手）を受け付ける。複数を指定したときは 1 件ずつ直列に進める。
- **自動モード（`--auto`）**: 質問せずに推奨案を採用して進める。自動で決めたことは `specs/<NNN-name>/auto-decisions.md` に記録する。マージの競合や中止などでは止まり、範囲指定ならその機能を飛ばして次に進む（詳細は `speckit-worktree` の §6）。
- **片付け（S12）**: リポジトリのルートで実行する。実装工程では、`tasks.md` に未完了のタスクが残っているとマージの前に止まり、残してよいかを確認する。

進捗の確認と中止は、ヘルパースクリプトでも行える（Windows で `python3` がない場合は `python` か `py -3`）。

```bash
H=".claude/skills/speckit-worktree/scripts/worktree_helper.py"
python3 $H status                 # 全フィーチャーの仕様・実装・worktree の状況
python3 $H next --phase all       # 次に着手すべきフィーチャー
python3 $H abort 002              # 破棄する対象の確認（実際に破棄するには --yes）
```

Windows の PowerShell では次のようになる。

```powershell
$H = ".claude\skills\speckit-worktree\scripts\worktree_helper.py"
py -3 $H status
```

## scaffold の更新

- スキルを直すときは `skills/speckit/` のファイルを編集する。各エージェントのスキルディレクトリはシンボリックリンクなので、編集はすべてのエージェントに反映される。
- 新しいスキルを追加したときは、`.claude/skills/`、`.agents/skills/`、`.kiro/skills/` のそれぞれに相対シンボリックリンクを張る。

  ```bash
  for d in .claude/skills .agents/skills .kiro/skills; do
    ln -s ../../skills/speckit/<スキル名> "$d/<スキル名>"
  done
  ```

  Windows の PowerShell では、開発者モードを有効にしたうえで次のようにする。

  ```powershell
  foreach ($d in ".claude\skills", ".agents\skills", ".kiro\skills") {
    New-Item -ItemType SymbolicLink -Path "$d\<スキル名>" -Target "..\..\skills\speckit\<スキル名>"
  }
  ```

- テストは `tool/` で実行する。worktree 管理のスクリプト、`validate.py`、`plan.py`、`build_pptx.py`、`new-speckit-project` のテストが含まれる。pptx の生成のテストは python-pptx があるときだけ動くので、uv で依存を足して実行する。

  ```bash
  cd tool && uv run --no-project --with python-pptx --with pyyaml python -m unittest discover -s tests
  ```

  GitHub に push すると、`.github/workflows/scaffold-tests.yml` が Ubuntu、macOS、Windows と Python 3.9、3.12 の組み合わせで同じテストを実行する。このワークフローは scaffold の開発用なので、`new-speckit-project` は新規プロジェクトに持ち込まない。
- **このリポジトリでも、作成したプロジェクトでも、次の Specify CLI のコマンドを実行しない。** スキルがシンボリックリンクのため、リンク先の `skills/speckit/` がエージェント固有の内容で上書きされる。
  - `specify init --here --force`
  - `specify integration install` / `upgrade` / `switch` / `uninstall`（`uninstall` は共有スキルの実体まで消すおそれがある）

  エージェント向けの manifest（`.specify/integrations/*.manifest.json`）は、今のスキルの実体と対応しないため置いていない。

  Spec Kit を新しい版にするときは、別のディレクトリで `specify init --integration codex --script py` と `specify init --integration opencode --script py` を実行し、生成されたスキル、`.specify/scripts/python/`、`.opencode/commands/` を確かめてから取り込む。

## ライセンス

- この scaffold は [MIT License](LICENSE) で公開している。
- [GitHub Spec Kit](https://github.com/github/spec-kit)（MIT License、Copyright GitHub, Inc.）から生成したファイルを含む（`.specify/`、Spec Kit の標準スキル、`.opencode/commands/`）。著作権表示と許諾文は [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) にある。
- `new-speckit-project` で作るプロジェクトには、`THIRD_PARTY_NOTICES.md` を持ち込み、`LICENSE` は持ち込まない。プロジェクト自体のライセンスは、作った人が決める。

## 注意点

- **Codex CLI**: 標準のサンドボックス（`workspace-write`）では、`.git` が読み取り専用になり、ネットワークも使えない。そのため、コミットやブランチの作成、出典付きの Web 調査、依存パッケージの取得ができない。`new-speckit-project` は、サンドボックスを保ったまま、`.git` への書き込み、Web 検索、ネットワークを有効にして起動する。手動で起動するときは、次のように指定する。

  ```bash
  codex --sandbox workspace-write --search \
    -c "sandbox_workspace_write.writable_roots=['$(pwd)/.git']" \
    -c "sandbox_workspace_write.network_access=true"
  ```

- **Windows**: Git と Python があれば、bash なしで動く。
  - `python3` がない場合、エージェントは steering のルールに従って `python` か `py -3` に読み替える。
  - シンボリックリンクを使うには、開発者モードを有効にするか、管理者権限が必要である。使えない環境では、`new-speckit-project` がスキルを実体のコピーに切り替える。その場合、スキルを更新するときは各エージェントのスキルディレクトリにも反映する。
  - 各エージェントの CLI が Windows に対応しているかは、それぞれの CLI による。
- **opencode**: `.claude/skills/` と `.agents/skills/` の両方から同じスキルを読み込むため、起動時に `duplicate skill name` の警告が出る。動作には影響しない。
- **`.worktrees/`**: `.gitignore` で除外している。除外を外すと、worktree 管理のスクリプトが S1 で止まる。
- **既定のブランチ**: スクリプトは既定のブランチを `main` とみなす。別の名前のリポジトリで使うときは、環境変数 `SPECKIT_MAIN_BRANCH` にその名前を指定する。

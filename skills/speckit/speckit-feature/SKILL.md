---
name: "speckit-feature"
description: "フィーチャーの仕様工程を実行するスキル。Git worktree の準備（既存があれば再利用して続きから再開）、仕様作成（speckit-specify）、仕様明確化（speckit-clarify x 2）、詳細設計（speckit-plan）、タスク分解（speckit-tasks）、整合性検証（speckit-analyze x 3）を行い、main へのマージと後片付けまでを実行する。実装は speckit-coding、通しは speckit-all で行う。"
argument-hint: "フィーチャー番号または範囲（例: 001, 002, 002-005, all, または省略して次の未着手）"
compatibility: "Requires git, spec-kit project structure with .specify/ directory"
user-invocable: true
disable-model-invocation: false
---

# speckit-feature スキル（仕様工程: S1 → S2〜S7-3 → S12）

フィーチャーごとに、worktree の準備、仕様作成、明確化 2 回、詳細設計、タスク分解、整合性検証 3 回を行い、仕様・設計・タスクを `main` にマージする。

- 実装工程（S8〜S11）は [`speckit-coding`](../speckit-coding/SKILL.md) が担当する。
- 仕様から実装までを 1 つの worktree で通して行う場合は [`speckit-all`](../speckit-all/SKILL.md) を使う。`speckit-all` は、このファイルの「§3 本体」だけを実行する。

**ステップ番号、ヘルパースクリプト（`$HELPER`）、再開、安全規則、対話、引数の解釈は [`speckit-worktree`](../speckit-worktree/SKILL.md) に従う。** 作業を始める前に必ず読むこと。

## 1. ユーザー入力・引数

```text
$ARGUMENTS
```

引数の解釈と複数フィーチャーの進め方は `speckit-worktree` の §5 に従う。自動検出では `--phase spec` を使う。

## 2. 実行の流れ（単独実行）

対象フィーチャーごとに、次を順に行う。

1. **S1 準備**: `speckit-worktree` §3「S1 準備」に従い、`$HELPER ensure <feature> --phase spec` を実行する。
2. **本体**: 下の §3 の S2〜S7-3 のうち、`NEXT_STEP` 以降を順に実行する。
3. **S12 片付け**: `speckit-worktree` §3「S12 片付け」に従い、`$HELPER finish <FEATURE_NAME> --phase spec` を実行する。
4. 次のフィーチャーがあれば 1 に戻る。

## 3. 本体（S2〜S7-3）

作業場所は `WORKTREE_DIR`、仕様ディレクトリは `specs/<FEATURE_NAME>`（以下 `FEATURE_DIR`）である。各ステップの最後に `speckit-worktree` §2 の subject で `checkpoint` を記録する。

### 入力情報

各ステップで、存在するものを参照する。

- 機能概要 `docs/feature/<FEATURE_NAME>.md`（例: `docs/feature/001-clinic-setup.md`）。なければ旧形式の `docs/feature/<slug>.md`（`<slug>` は `FEATURE_NAME` から先頭の番号を除いたもの）。`speckit-concept-2-feature` の出力で、末尾の「`/speckit-specify` に渡す記述案」を S2 の入力に使う。
- 前提メモ `docs/feature/premises.md`、着手順序 `docs/feature/spec_order.md`
- コアコンセプト `docs/concept/`（なければ `docs/conpect/`）
- プロジェクト憲章 `.specify/memory/constitution.md`
- 引数やプロンプトで与えられた追加指示

機能概要がなく、追加指示もない場合は、何を作るかをユーザーに質問してから S2 に進む。

### S2: 仕様作成（speckit-specify）

1. `speckit-specify` スキルの手順に従い、仕様書 `FEATURE_DIR/spec.md` を作る。
   - `SPECIFY_FEATURE_DIRECTORY` には `specs/<FEATURE_NAME>` を明示的に指定する。worktree はすでにこのディレクトリを前提に作られているため、新しい番号のディレクトリを作らない。
   - **WHAT（何を提供するか）と WHY（なぜ必要か）**に集中し、HOW（言語、フレームワーク、DB などの実装詳細）は書かない。
   - ユーザーストーリー（P1、P2、P3… の優先順。ストーリーごとのゴールと受入基準）
   - 機能要件（FR-001、FR-002… 各要件が検証可能であること）
   - 測定可能な成功基準（SC-001、SC-002… 時間、件数、率などの技術に依存しない指標）
   - 主要エンティティ、エッジケース、前提条件
2. 品質チェックリスト `FEATURE_DIR/checklists/requirements.md` を作り、初回の検証を行う。
3. `checkpoint <FEATURE_NAME> S2` を記録する。

> 💬 仕様上の前提条件やスコープに疑問がある場合は、ユーザーに質問して確認する。

### S3: 仕様の明確化 1 回目（コア要件・振る舞い）

1. `speckit-clarify` スキルの手順で `spec.md` をスキャンし、機能スコープ、ユーザージャーニー、ドメインのデータモデル、必須の制約などの曖昧さと決定漏れを特定する。
2. 最重要の論点（最大 3〜5 問）を、推奨選択肢（`**Recommended:**`）とその理由を添えて質問する。
3. 確定した回答を `spec.md` の `## Clarifications` > `### Session YYYY-MM-DD (Round 1)` に記録し、本文の該当箇所（機能要件、ユーザーストーリー、データモデルなど）に反映する。
4. `checklists/requirements.md` を再評価して更新する。
5. `checkpoint <FEATURE_NAME> S3` を記録する。

### S4: 仕様の明確化 2 回目（エッジケース・非機能・安全性）

1. 1 回目の決定事項を前提に、一段深い境界条件と例外系を洗い出す。
   - エラー処理と障害からの復旧
   - 非機能要件（応答時間の許容値、同時実行と競合の制御、オフラインやキャッシュの動作）
   - セキュリティと権限（権限の境界、認証情報の失効、監査ログ）
   - 外部連携の障害モード（遅延、到達不能、不正な応答）
2. 残る重要な論点を、推奨選択肢とともに質問する。
3. 回答を `### Session YYYY-MM-DD (Round 2)` に記録して本文に反映し、`checklists/requirements.md` を最終更新する。
4. `checkpoint <FEATURE_NAME> S4` を記録する。

### S5: 詳細設計と憲章チェック（speckit-plan）

`speckit-plan` スキルの手順に従い、明確化を経た `spec.md` と憲章に基づいて次の成果物を作る。

1. `FEATURE_DIR/plan.md`: 技術コンテキスト（アーキテクチャ、使用技術、ライブラリ、テスト・ビルドのコマンド）と憲章チェック（各原則、品質ゲートとの整合）
2. `FEATURE_DIR/research.md`: 不明点の調査、技術選定の決定事項（Decision）、選定理由（Rationale）、比較した代替案（Alternatives considered）
3. `FEATURE_DIR/data-model.md`: エンティティ、属性と型、リレーション、整合性制約、状態遷移
4. `FEATURE_DIR/contracts/`: API、コマンド、UI コンポーネントなど、外部に公開するインターフェースの契約
5. `FEATURE_DIR/quickstart.md`: 動作確認のシナリオ、テストの実行手順、期待結果

作り終えたら `checkpoint <FEATURE_NAME> S5` を記録する。

> 💬 アーキテクチャのトレードオフやライブラリの選定で判断が必要な場合は、ユーザーに質問する。

### S6: タスク分解（speckit-tasks）

`speckit-tasks` スキルの手順に従い、設計成果物と `spec.md` のユーザーストーリーに基づいて `FEATURE_DIR/tasks.md` を作る。

- 形式: `- [ ] [TaskID] [P?] [Story?] 説明とファイルパス`
- フェーズ構成: Phase 1 Setup → Phase 2 Foundational → Phase 3 以降 User Stories（優先順）→ Final Phase Polish & Cross-Cutting Concerns
- ストーリー間の依存関係、`[P]` タスクの並行実行例、MVP の範囲を示す。

作り終えたら `checkpoint <FEATURE_NAME> S6` を記録する。

### S7-1〜S7-3: 整合性検証 3 回（speckit-analyze）

`tasks.md`、`spec.md`、`plan.md`、憲章を対象に、`speckit-analyze` スキルの手順で分析と是正を 3 回、直列に行う。各回の終わりに `checkpoint` を記録する。指摘が 0 件で変更がなくても記録する。

1. **S7-1（重大課題・憲章整合・カバレッジ）**: 憲章の MUST 原則との矛盾（CRITICAL）、要件（FR-、SC-）に対応するタスクの未割り当て、仕様と設計の大きな乖離を検出して直す。
2. **S7-2（詳細整合・依存関係・ファイルパス）**: 用語の揺れ、エンティティ定義の不一致、タスクの依存順序の矛盾、ファイルパスの参照のずれを直す。
3. **S7-3（最終確認）**: CRITICAL、HIGH、MEDIUM の不整合が 0 件、憲章違反が 0 件、タスクのカバレッジが 100% であることを確かめる。満たさない場合は直してから記録する。

> 💬 修正方針にトレードオフや判断が必要な場合は、ユーザーに質問する。

## 4. 完了報告

各フィーチャーの完了時と、指定範囲の全体の完了時に、次を報告する。

- 完了したフィーチャー名と番号、マージコミット
- 各ステップの要約（仕様、設計、タスクの成果物）
- clarify 2 回で確定した重要な決定事項
- analyze 3 回の検証結果
- 飛ばした、または中断したフィーチャーとその理由
- 次の案内: 実装は `speckit-coding <FEATURE_NAME>`。仕様が未着手のフィーチャーは `$HELPER next --phase spec` の結果

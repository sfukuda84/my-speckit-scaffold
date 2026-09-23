---
name: "speckit-review"
description: "Review code changes (commits, branches, or working diffs) along two distinct axes: Standards (security, performance, TypeScript/code quality, Fowler smells, repo rules) and Spec (conformance with spec.md, plan.md, and constitution.md). Pinpoints issues with file paths, line numbers, severity, and concrete fix suggestions. Use when reviewing code, PRs, commits, or feature branches."
argument-hint: "対象コミット・ブランチ・差分（例: HEAD~1, main...HEAD, staged, または省略で直近変更）"
user-invocable: true
disable-model-invocation: false
---

# speckit-review スキル（2 軸コードレビュー＆品質保証ガイド）

本スキルは、Claude Code における高品質なコードレビューの思想に基づき、対象の変更差分を **2 つの独立した評価軸（Standards 軸 と Spec 軸）** で厳密に検証・修正するエージェントネイティブなレビューガイドラインです。

外部 CLI コマンドに依存せず、エージェント自身のコード探索・分析機能とテスト実行ツールを用いて完結します。

---

## 1. 2 つのレビュー評価軸（Two-Axis Review）

コードが一方の軸を満たしていても、もう一方の軸で破綻しているケース（「規約には従っているが仕様と違う」「仕様通りだが脆弱で保守不能」）を防ぐため、常に 2 軸を独立して評価します。

### 【軸 A: Standards（規約・品質・セキュリティ・パフォーマンス）】
- **セキュリティ脆弱性**:
  - SQL / NoSQL インジェクション（生クエリやパラメータ不備）
  - 認証・認可の境界検証（未認証アクセス、IDOR、ロール偽装）
  - 機密情報（APIキー、シークレット）の混入
  - 入力値バリデーション・サニタイズ漏れ
- **パフォーマンス・スケーラビリティ**:
  - N+1 クエリ、非効率なループ内 DB アクセス
  - PostGIS 空間インデックス（GiST）の適切な活用（`ST_DWithin` 等の空間関数がインデックスに乗るか）
  - 不要な全件フェッチ、メモリリーク、不要な再レンダリング
- **型安全性・コード品質**:
  - TypeScript 型検査（`any` の乱用排除、`unknown` や型ガードの適切な利用）
  - エラーハンドリングの網羅性（Promise catch 漏れ、例外の握りつぶし防止）
  - DRY 原則、単一責任の原則
- **コードの匂い（Fowler Code Smells）**:
  - **Duplicated Code**: 同じロジックの重複
  - **Feature Envy**: 他のオブジェクトやテーブルの責務に過剰に立ち入る処理
  - **Data Clumps / Primitive Obsession**: ドメイン概念（UUID、座標、クーポンコード等）の生プリミティブ乱用
  - **Speculative Generality**: 現状の仕様にない不要な先回り・過度な抽象化

### 【軸 B: Spec（仕様・受入基準・設計整合性）】
- **機能要件の充足度**:
  - `specs/<FEATURE>/spec.md` の機能要件（FR-xxx）およびユーザーストーリーの受入基準を満たしているか？
  - 実装漏れ（Missing requirements）やエッジケースの放置がないか？
- **スコープクリープの排除**:
  - 仕様に合意されていない余計な機能・挙動が勝手に混入していないか？
- **アーキテクチャ・憲章整合性**:
  - `specs/<FEATURE>/plan.md`、`data-model.md`、`contracts/*` の設計契約に忠実か？
  - プロジェクト憲章（`.specify/memory/constitution.md`）の原則に準拠しているか？

---

## 2. レビュー対象の特定（Diff Resolution）

ユーザー入力または実行コンテキストから対象差分を特定します：

| 指定パターン | 差分コマンド | 主な用途 |
|---|---|---|
| **直近のコミット** | `git diff HEAD~1` | ステップ 8 の実装コミット直後のレビュー |
| **ブランチ全体** | `git diff main...HEAD` | フィーチャーブランチと main との全体差分レビュー |
| **未コミット変更** | `git diff` または `git diff --cached` | 作業ツリーの変更差分レビュー |
| **ファイル・パス指定** | `git diff <path>` | 特定ファイル・モジュールに絞ったレビュー |
| **引数なし** | ブランチ差分があれば `main...HEAD`、なければ `HEAD~1` | 自動判別 |

---

## 3. レビューの実行手順

1. **差分とコンテキストのロード**:
   - `git diff <range>` を取得し、変更されたファイル一覧・行を把握。
   - 関連ドキュメント（`specs/<FEATURE>/spec.md`, `plan.md`, `constitution.md`）を読み込む。
2. **Standards 軸 ＆ Spec 軸の精査**:
   - 各ファイルの変更行（および周辺コンテキスト）を読み、上記 2 軸の観点で問題点を抽出。
   - 問題ごとに重大度（**CRITICAL**, **HIGH**, **MEDIUM**, **LOW**）を割り当て。
3. **レビューレポートの出力**:
   - 以下の Markdown フォーマットで報告。

```markdown
# コードレビュー結果報告（Code Review Report）

## レビュー対象
- **差分範囲**: `git diff <range>` (X files changed, +Y / -Z lines)
- **仕様ドキュメント**: `specs/<FEATURE>/spec.md`

## 課題サマリー
- **CRITICAL**: X 件（セキュリティ脆弱性、憲章違反、仕様未達）
- **HIGH**: Y 件（性能問題、重大な型不整合、エッジケース未考慮）
- **MEDIUM**: Z 件（コードの匂い、リファクタリング推奨）
- **LOW**: W 件（軽微な改善提案）

---

### 【Standards（規約・品質・セキュリティ・パフォーマンス）】

#### [CRITICAL/HIGH/MEDIUM/LOW] [カテゴリ] 課題タイトル
- **対象箇所**: [`src/path/to/file.ts#L25-L35`](file:///absolute/path/to/file.ts#L25-L35)
- **問題の説明**: 何がなぜ問題なのか、発生しうるリスク。
- **改善コード案**:
```typescript
// 修正後コード
```

---

### 【Spec（仕様・受入基準整合性）】

#### [CRITICAL/HIGH/MEDIUM/LOW] 要件との乖離・不足
- **対象要件**: FR-002 / User Story 1 受入基準
- **現状の実装**: ...
- **求められる挙動**: ...
- **推奨対応**: ...
```

---

## 4. 指摘事項の修正（Remediation）と対話

1. **優先対応**:
   - **CRITICAL / HIGH** の指摘は原則としてその場で修正コードを適用します。
2. **対話的確認**:
   - リファクタリングの方針に複数の選択肢がある場合や、仕様の解釈・設計トレードオフについて判断が必要な場合は、**ユーザーに対話的に質問（推奨案 `**Recommended:**` を添えて）を行い、合意を得てから修正**します。
3. **テスト検証**:
   - 修正適用後、必ずテストコマンド（例: `npm test`）を実行し、すべてのテストが PASS すること（リグレッションがないこと）を確認します。

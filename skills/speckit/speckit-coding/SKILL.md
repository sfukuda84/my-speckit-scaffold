---
name: "speckit-coding"
description: "フィーチャーの実装工程を実行するスキル。Git worktree の準備（既存があれば再利用して続きから再開）、実装（speckit-implement）、仕様収束（speckit-converge）、2 軸コードレビュー（speckit-review）と修正、再レビューと修正を行い、main へのマージと後片付けまでを実行する。spec.md・plan.md・tasks.md が必要で、なければ speckit-feature を案内する。"
argument-hint: "フィーチャー番号または範囲と、任意の --auto（例: 001, 002-005, all, all --auto, または省略して次の未実装）"
compatibility: "Requires git, spec-kit project structure with .specify/ directory"
user-invocable: true
disable-model-invocation: false
---

# speckit-coding スキル（実装工程: S1 → S8〜S11 → S12）

仕様工程（[`speckit-feature`](../speckit-feature/SKILL.md)）で作った `spec.md`、`plan.md`、`tasks.md` に基づき、実装、収束の検証、2 回のコードレビューと修正を行い、`main` にマージする。

- 仕様から実装までを 1 つの worktree で通して行う場合は [`speckit-all`](../speckit-all/SKILL.md) を使う。`speckit-all` は、このファイルの「§3 本体」だけを実行する。

**ステップ番号、ヘルパースクリプト（`$HELPER`）、再開、安全規則、対話、引数の解釈は [`speckit-worktree`](../speckit-worktree/SKILL.md) に従う。** 作業を始める前に必ず読むこと。

## 1. ユーザー入力・引数

```text
$ARGUMENTS
```

引数の解釈と複数フィーチャーの進め方は `speckit-worktree` の §5 に従う。`--auto` があるときは、下の 💬 の質問も含めて `speckit-worktree` §6 の自動モードで進める。自動検出では `--phase coding` を使い、`main` の `tasks.md` に未完了のタスク（`- [ ]`）が残っているフィーチャーを対象にする。

## 2. 実行の流れ（単独実行）

対象フィーチャーごとに、次を順に行う。

1. **S1 準備**: `speckit-worktree` §3「S1 準備」に従い、`$HELPER ensure <feature> --phase coding` を実行する。
   - 仕様工程の途中の worktree がある場合は `SPEC_INCOMPLETE`、仕様がどこにもない場合は `SPEC_MISSING` で止まる。そのときは何も作らずに、`speckit-feature` または `speckit-all` の実行を案内する。
   - worktree がなく、仕様が `main` にマージ済みの場合は、`main` から新しい worktree を作る。
   - `speckit-all` などで仕様工程を終えた worktree が残っている場合は、それを再利用する。
2. **本体**: 下の §3 の S8〜S11 のうち、`NEXT_STEP` 以降を順に実行する。
3. **S12 片付け**: `speckit-worktree` §3「S12 片付け」に従い、`$HELPER finish <FEATURE_NAME> --phase coding` を実行する。
4. 次のフィーチャーがあれば 1 に戻る。

## 3. 本体（S8〜S11）

作業場所は `WORKTREE_DIR`、仕様ディレクトリは `specs/<FEATURE_NAME>`（以下 `FEATURE_DIR`）である。各ステップの最後に `speckit-worktree` §2 の subject で `checkpoint` を記録する。

テスト、ビルド、リンターのコマンドは `speckit-worktree` §4 に従って判断する。

### S8: 実装（speckit-implement）

1. `speckit-implement` スキルの手順に従い、`FEATURE_DIR/tasks.md` の全タスクを実装する。
   - Phase 1（Setup）→ Phase 2（Foundational）→ Phase 3 以降（User Stories）→ Final Phase（Polish）の順を守る。
   - テストファースト（TDD）で進め、契約、エンティティ、ロジックのテストを書いて実行する。
   - タスクが終わるごとに `tasks.md` のチェックボックスを `- [x]` に更新する。
   - 途中で区切りのよいところでは、trailer なしの通常のコミットを作ってよい。
2. テスト、ビルド、リンターを実行し、すべて通ることを確かめる。
3. `checkpoint <FEATURE_NAME> S8` を記録する。

> 💬 実装中に仕様の隙間、例外時の挙動、設計方針の分岐が出てきた場合は、ユーザーに質問して合意を取る。仕様を変える場合は、コードだけでなく `spec.md`、`plan.md`、`tasks.md` にも反映する。

### S9: 仕様収束（speckit-converge）

1. `speckit-converge` スキルの手順に従い、コードベースを `spec.md`、`plan.md`、`tasks.md`、憲章と照合する。
   - ギャップの種類（`missing`: 未実装、`partial`: 不完全、`contradicts`: 矛盾、`unrequested`: 仕様にない追加）を調べる。
   - テストの不足や、考慮されていないエッジケースも併せて調べる。
2. ギャップがある場合は、`tasks.md` の末尾に `## Phase N: Convergence` として不足タスクを追加し、S8 と同じ手順で実装とテストを行う。もう一度照合し、「✅ Converged」になるまで繰り返す。
3. 未達のギャップが 0 件になったら、`checkpoint <FEATURE_NAME> S9` を記録する。

> 💬 ギャップの解消方針や仕様との乖離について判断が必要な場合は、ユーザーに質問する。

### S10: コードレビュー 1 回目と修正（speckit-review）

[`speckit-review`](../speckit-review/SKILL.md) スキルの手順に従い、2 軸のコードレビューを行う。外部の CLI には依存しない。

1. レビュー対象の差分として `git diff main...HEAD` を取得する（既定のブランチが main 以外で `SPECKIT_MAIN_BRANCH` を指定している場合は、その名前に読み替える。以下同じ）。
2. 2 軸でレビューする。
   - **Standards 軸**: セキュリティ上の脆弱性（インジェクション、認可漏れ、シークレット）、性能（不要な繰り返し処理、N+1 クエリ、インデックスの活用）、型安全性、コードの臭い（重複、肥大化）
   - **Spec 軸**: `spec.md` の機能要件と受入基準を満たしているか、仕様外の追加がないか、`plan.md`、`contracts/`、憲章と設計が整合しているか
3. CRITICAL、HIGH、MEDIUM の指摘を直し、テストがすべて通ることを確かめる。
4. `checkpoint <FEATURE_NAME> S10` を記録する。

> 💬 指摘への対応方針（リファクタリングの方針や優先度）に判断が必要な場合は、推奨案を添えて質問し、合意を取る。

### S11: 再レビューと修正（speckit-review）

S10 の修正が既存のロジックを壊していないか、新たな不整合やエッジケースの抜けがないかを確かめるため、2 回目のレビューを行う。

1. S10 の修正差分（`git diff HEAD~1`）と全体の差分（`git diff main...HEAD`）を対象に、もう一度 `speckit-review` スキルを実行する。
2. 二次的な不整合、型定義の甘さ、考慮されていないエッジケース、テストの網羅性を最終確認する。
3. 残っている指摘を直し、テストがすべて通ることを確かめる。修正がなくても次へ進む。
4. `checkpoint <FEATURE_NAME> S11` を記録する。

> 💬 残っている指摘への対応の要否について確認が必要な場合は、ユーザーに質問する。

## 4. 完了報告

各フィーチャーの完了時と、指定範囲の全体の完了時に、次を報告する。

- 完了したフィーチャー名と番号、マージコミット
- 実装の要約とテスト結果
- converge の検証結果（追加したタスクがあればその内容）
- レビュー 2 回で見つかって直した指摘
- 飛ばした、または中断したフィーチャーとその理由
- `--auto` のとき: 自動で採用した判断の要約（`auto-decisions.md`）と、止まったフィーチャーについてユーザーに判断してほしい事項
- 次の案内: `$HELPER next --phase coding` の結果（実装が未完了のフィーチャー）

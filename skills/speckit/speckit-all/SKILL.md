---
name: "speckit-all"
description: "フィーチャーの仕様工程と実装工程を 1 つの Git worktree で通して実行するスキル。worktree の準備（既存があれば再利用して続きから再開）、speckit-feature の仕様工程（specify・clarify x 2・plan・tasks・analyze x 3）、speckit-coding の実装工程（implement・converge・2 軸レビュー x 2）を途中でマージせずに続けて行い、最後に main へのマージと後片付けを行う。--auto を付けると、質問せずに推奨案を採用して進める。"
argument-hint: "フィーチャー番号または範囲と、任意の --auto（例: 001, 002-005, all, all --auto, または省略して次の未完了）"
compatibility: "Requires git, spec-kit project structure with .specify/ directory"
user-invocable: true
disable-model-invocation: false
---

# speckit-all スキル（通し: S1 → S2〜S11 → S12）

仕様工程と実装工程を、1 つの worktree の中で途中マージなしに通して実行する。本体の手順はこのファイルには書かず、次の 2 つのファイルの「§3 本体」をそのまま使う。

- 仕様工程 S2〜S7-3: [`speckit-feature` の §3](../speckit-feature/SKILL.md)
- 実装工程 S8〜S11: [`speckit-coding` の §3](../speckit-coding/SKILL.md)

**ステップ番号、ヘルパースクリプト（`$HELPER`）、再開、安全規則、対話、引数の解釈は [`speckit-worktree`](../speckit-worktree/SKILL.md) に従う。** 作業を始める前に、`speckit-worktree`、`speckit-feature`、`speckit-coding` の 3 つの SKILL.md を読むこと。

## 1. ユーザー入力・引数

```text
$ARGUMENTS
```

引数の解釈と複数フィーチャーの進め方は `speckit-worktree` の §5 に従う。自動検出では `--phase all` を使う。

引数に `--auto` があるときは、仕様工程から実装工程、S12 までのすべての質問を `speckit-worktree` §6 の自動モードで扱う。`speckit-feature` と `speckit-coding` の本文にある 💬 の質問も、質問せずに推奨案を採用する。自動モードでも止まる場面（マージの競合など）では、§6「止まったときの扱い」に従う。

## 2. 実行の流れ

対象フィーチャーごとに、次を順に行う。

1. **S1 準備**: `speckit-worktree` §3「S1 準備」に従い、`$HELPER ensure <feature> --phase all` を実行する。
   - 仕様がすでに `main` にマージ済みのフィーチャーは、S2〜S7-3 が完了済みと判定され、`NEXT_STEP` が S8 になる。
2. **仕様工程**: `speckit-feature` の §3 の S2〜S7-3 のうち、`NEXT_STEP` 以降を順に実行する。
   - `speckit-feature` の §2（S1 と S12）は実行しない。**S7-3 の後で `finish` を実行せず、マージしないこと。**
3. **実装工程**: 同じ worktree のまま、`speckit-coding` の §3 の S8〜S11 を順に実行する。
   - `speckit-coding` の §2（S1 と S12）は実行しない。worktree を作り直さないこと。
4. **S12 片付け**: `speckit-worktree` §3「S12 片付け」に従い、`$HELPER finish <FEATURE_NAME> --phase all` を実行する。
5. 次のフィーチャーがあれば 1 に戻る。

途中で中断した場合は、もう一度 `speckit-all` を実行すれば、残っている worktree を使って続きのステップから再開する。仕様工程の途中なら `speckit-feature`、実装工程の途中なら `speckit-coding` で再開することもできる。その場合は、再開したスキルの S12 で `main` にマージされる。

## 3. 完了報告

各フィーチャーの完了時と、指定範囲の全体の完了時に、`speckit-feature` §4 と `speckit-coding` §4 の項目をまとめて報告する。

- 完了したフィーチャー名と番号、マージコミット
- 仕様工程の要約（clarify で確定した決定事項、analyze の検証結果）
- 実装工程の要約（実装内容、テスト結果、converge の結果、レビューで直した指摘）
- 残っている `[人]` のタスク（`finish` の `HUMAN_TASKS_PENDING`）と、片付けた後の手順（`speckit-worktree` §3「人のタスクの片付け」）
- 飛ばした、または中断したフィーチャーとその理由
- `--auto` のとき: 自動で採用した判断の要約（`auto-decisions.md`）と、止まったフィーチャーについてユーザーに判断してほしい事項
- 次の案内: `$HELPER next --phase all` の結果

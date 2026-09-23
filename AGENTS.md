# AGENTS.md

このプロジェクトのエージェント向けルールは `.kiro/steering/` で一元管理している。作業を始める前に、以下のファイルをすべて読み込み、その内容に必ず従うこと。

- `.kiro/steering/language.md` — 応答と成果物は日本語で書く（必須）
- `.kiro/steering/spec-driven-development.md` — Spec Kit による仕様駆動開発のルールとワークフロー

ルールを追加・変更するときは `.kiro/steering/` のファイルを編集する。このファイル（AGENTS.md）にルールを直接書かない。新しい steering ファイルを追加したときは、上のリストにも 1 行追加する。

opencode は `opencode.json` の `instructions` で `.kiro/steering/*.md` を直接読み込むため、steering ファイルを追加しても `opencode.json` の変更は不要である。

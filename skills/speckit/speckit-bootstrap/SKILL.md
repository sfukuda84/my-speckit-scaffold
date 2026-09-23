---
name: "speckit-bootstrap"
description: "新規プロジェクトの立ち上げを通しで行う統括スキル。docs/concept/ のコアコンセプトから、機能への仕分け（speckit-concept-2-feature）、アーキテクチャと技術選定（speckit-architecture）、憲章（speckit-constitution）、共通基盤（speckit-common-feature）、非機能要件（speckit-nfr-feature）を順に実行し、最後に全体を検証する。ステップごとにコミットし、中断しても続きから再開できる。new-speckit-project コマンドから起動されるほか、「プロジェクトを立ち上げて」「bootstrap して」と言われたとき、または /speckit-bootstrap と打たれたときに使う。"
argument-hint: "[省略可。コアコンセプトの追記や、各ステップへの追加の希望]"
compatibility: "Requires git and Python 3.9+, spec-kit project structure with .specify/ directory"
user-invocable: true
disable-model-invocation: false
---

# speckit-bootstrap スキル（新規プロジェクトの立ち上げ: B0 → B6）

コアコンセプトから、仕様化と実装に入れる状態（機能の一覧、アーキテクチャ、憲章、共通基盤、非機能要件）までを、1 つの流れで作る。各ステップの中身は、それぞれのスキルの SKILL.md に従う。このファイルには順番と引き継ぎだけを書く。

## 1. 引数

```text
$ARGUMENTS
```

引数があれば、コアコンセプトへの追記、または各ステップへの追加の希望として扱う。

## 2. ステップ

| ステップ | 使うスキル | 完了の条件（成果物） | コミットの subject |
|---|---|---|---|
| B0 | （このスキル） | `docs/concept/` にコアコンセプトがある | （コミットなし） |
| B1 | [`speckit-concept-2-feature`](../speckit-concept-2-feature/SKILL.md) | `docs/feature/` 一式（`premises.md`、`README.md`、`spec_order.md`、`001-*.md` 以降） | `docs(bootstrap): B1 concept to features` |
| B2 | [`speckit-architecture`](../speckit-architecture/SKILL.md) | `docs/architecture.md` | `docs(bootstrap): B2 architecture` |
| B3 | `speckit-constitution` | `.specify/memory/constitution.md`（テンプレートの `[PROJECT_NAME]` などが残っていない） | `docs(bootstrap): B3 constitution` |
| B4 | [`speckit-common-feature`](../speckit-common-feature/SKILL.md) | `docs/feature/000-app-basic.md` | `docs(bootstrap): B4 common feature` |
| B5 | [`speckit-nfr-feature`](../speckit-nfr-feature/SKILL.md) | `docs/nfr.md` と `docs/feature/999-app-nfr.md` | `docs(bootstrap): B5 non-functional requirements` |
| B6 | （このスキル） | 検証のエラーが 0 件 | `docs(bootstrap): B6 validate` |

## 3. 進捗の記録と再開

- 各ステップが終わったら、次のようにコミットする。変更がなくても空コミットで記録する。

  ```bash
  git add -A
  git commit --allow-empty -m "<§2 の subject>" -m "Speckit-Bootstrap: <ステップ>"
  ```

- 開始時に、次のコマンドで完了済みのステップを調べる（`grep` を使わないので Windows でも動く）。

  ```bash
  git log --format="%(trailers:key=Speckit-Bootstrap,valueonly)"
  ```

- 完了済みのステップは飛ばし、最初の未完了のステップから再開する。記録がなくても成果物がそろっているステップは、内容を確かめ、完了として記録してよいかをユーザーに確認する。
- 再開する場合は、完了済みのステップと再開するステップをユーザーに示してから進める。

## 4. 手順

### B0: 事前確認

1. Git リポジトリのルートで、ブランチが `main` であり、未コミットの変更がないことを確かめる。満たさない場合は、ユーザーに状況を示して対応を確認する。
2. `docs/concept/` に、`.gitkeep` 以外のコアコンセプトのファイルがあることを確かめる。ない場合は、サービスのコアコンセプト（誰の、どんな課題を、どう解決するか）を質問し、`docs/concept/core-concept.md` に書いてコミットする。
3. 引数でコンセプトへの追記があれば、`docs/concept/core-concept.md` の末尾に「追記（日付）」の節として足す。

### B1: コンセプトを機能に仕分ける

`speckit-concept-2-feature` の手順を、新規モードで最後まで行う。ヒアリング、競合調査、分割案の合意、書き出し、検証を省かない。

- 認証やメール送信などの共通機能は機能にせず、`premises.md` の「共通基盤の候補」に記録させる（B4 で使う）。
- 番号 `000` と `999` は使わない（B4 と B5 で使う）。

### B2: アーキテクチャと技術選定

`speckit-architecture` の手順を最後まで行う。ヒアリング、3 系統の比較、案の選択、`docs/architecture.md` の書き出しを省かない。

### B3: 憲章

`speckit-constitution` の手順で `.specify/memory/constitution.md` を作る。原則の案を作るときは、次を入力として渡し、ユーザーの確認を取る。

- 仕様駆動開発と言語のルール（`.kiro/steering/` の各ファイル）
- `docs/architecture.md` の技術スタックと構成。例: 「技術スタックは docs/architecture.md に従う。変える場合は speckit-architecture の見直しを経る」
- 非機能要件の参照。例: 「すべての機能は docs/nfr.md の横断要件を満たし、plan.md の憲章チェックで確かめる」（`docs/nfr.md` は B5 で作る）
- テストの方針（テストファーストにするかなど）は、ユーザーに質問して決める。

### B4: 共通基盤

`speckit-common-feature` の手順を最後まで行い、`docs/feature/000-app-basic.md` を作る。`spec_order.md` の先頭への追加と、各機能の依存の更新まで行う。

### B5: 非機能要件

`speckit-nfr-feature` の手順を最後まで行い、`docs/nfr.md` と `docs/feature/999-app-nfr.md` を作る。憲章に `docs/nfr.md` を参照する条項があることも確かめる。

### B6: 全体の検証

1. 機能一式を検証し、エラーが 0 件になるまで直す。

   ```bash
   python3 <skills>/speckit-concept-2-feature/scripts/validate.py docs/feature
   ```

   `<skills>` は、このスキルが置かれた skills ディレクトリである。`python3` がない環境では `python` または `py -3` に読み替える。

2. 次の整合を確かめる。食い違いがあれば、該当するスキルの更新モードで直すか、ユーザーに確認する。
   - `docs/architecture.md` の構成と、`docs/nfr.md` の目標値（構成と費用で達成できるか）
   - 憲章と、`docs/architecture.md`、`docs/nfr.md` の参照
   - `000-app-basic.md` と、`premises.md` の「共通基盤の候補」
   - `spec_order.md` の並び（`000` が先頭、`999` が MVP の最後）
3. コミットする。

## 5. 完了報告

- 作成したファイルの一覧
- 機能の数（MVP / 拡張）と、着手順の先頭 3 件
- 採用したアーキテクチャと、MVP 時の月額の概算
- 憲章の原則の要約
- 共通基盤（000）と運用基盤（999）の主な要求、`docs/nfr.md` の主な目標値
- 検証の結果（エラー、警告）
- 次の案内: `speckit-all`（引数なし）で、`000-app-basic` から 1 件ずつ仕様化と実装を進める

## 6. 規則

- 各ステップの中身は、それぞれのスキルの SKILL.md に従う。このスキルで手順を省いたり、ヒアリングを飛ばしたりしない。
- ユーザーが「このステップは後でやる」と明示した場合は、そのステップを飛ばして次に進んでよい。完了報告に、飛ばしたステップと影響を書く。飛ばしたステップは記録しない（再実行時に再開の対象になる）。
- 応答と成果物は、プロジェクトの言語ルール（`.kiro/steering/language.md`）に従う。

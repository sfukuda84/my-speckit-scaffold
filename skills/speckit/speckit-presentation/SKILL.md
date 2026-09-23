---
name: "speckit-presentation"
description: "docs/project.md（事業計画）と docs/concept/・docs/feature/ などの成果物から、読み手（社内の承認・投資家・顧客）に合わせた企画書を PowerPoint（.pptx）で作るスキル。スライドの内容は docs/presentation/<読み手>/slides.md に、見た目は docs/presentation/design.yaml に書き、同梱の build_pptx.py で pptx に変換する。数字はすべて成果物から取り、出典をスライドに入れる。「企画書を作って」「提案資料にして」「pptx にして」と言われたとき、または /speckit-presentation と打たれたときに使う。"
argument-hint: "[読み手: internal | investor | customer]（省略時は質問する）[追加の希望]"
compatibility: "Requires uv (or python-pptx and PyYAML); uses docs/project.md and other docs/ artifacts"
user-invocable: true
disable-model-invocation: false
---

# speckit-presentation スキル（成果物 → 企画書の pptx）

プロジェクトの成果物を材料に、読み手に合わせた企画書を作る。内容（`slides.md`）、見た目（`design.yaml`）、変換（`build_pptx.py`）を分け、pptx はいつでも作り直せるようにする。

## 0. 大原則

- **新しい事実を作らない。** 数字、目標、価格、スケジュールは、成果物（とくに `docs/project.md`）にあるものだけを使う。足りない情報があっても、ここで調べたり決めたりしない。事業計画の不足は `speckit-project`、機能の不足は `speckit-concept-2-feature` の更新モードで補うよう案内する。
- **数字には出典を付ける。** 数字を出すスライドには、`> 出典: <成果物のパスと節>` を書く。成果物が外部の資料を出典にしている場合は、その資料名も添える。
- **1 枚に 1 つの主張。** 見出しは話題名（「市場規模」）ではなく主張（「対象の市場は年 1.8 万件」）にする。
- **読み手に合わせて構成を変える。** §3 の構成に従う。
- **構成は書き出す前に合意を取る。**
- **pptx を手で直さない。** pptx は `slides.md` と `design.yaml` から作り直すので、PowerPoint で直した内容は次の生成で消える。直したい点は `slides.md` か `design.yaml` に反映する。
- ドキュメントとスライドは日本語で書く。

## 1. 引数と入出力

```text
$ARGUMENTS
```

第 1 引数は読み手（`internal`、`investor`、`customer`）。省略時は質問する。

| 入力 | 用途 | ない場合 |
|---|---|---|
| `docs/project.md` | 市場、価格、収支、KPI、スケジュール、体制、リスク | 停止して `speckit-project` を案内する |
| `docs/concept/`（`competitor.md`、`backlog.md` を含む） | 課題、競合、見送った候補 | 必須 |
| `docs/feature/`（`premises.md`、`spec_order.md`、機能ファイル） | 価値、差別化、機能の一覧と区分 | 機能のスライドを省く |
| `docs/architecture.md`、`docs/nfr.md` | 構成と費用、運用とセキュリティの方針 | 該当するスライドを省く |

| 出力 | 役割 |
|---|---|
| `docs/presentation/design.yaml` | デザインスペック。読み手ごとの版で共通。なければ [templates/design.yaml](./templates/design.yaml) から作る |
| `docs/presentation/<読み手>/slides.md` | スライドの内容と発表者ノート（中間成果物）。書き方は §4、見本は [templates/slides.md](./templates/slides.md) |
| `docs/presentation/<読み手>/proposal.pptx` | 企画書（最終成果物）。Git にコミットする |
| `docs/presentation/<読み手>/images/` | スライドに貼る画像（使う場合） |

`slides.md` がすでにある場合は、**更新モード**として §5 に従う。

## 2. 手順

### ステップ 1: 読み手と目的の確認

AskUserQuestion などで、次を確かめる（引数や既存の `slides.md` の front matter で決まっているものは聞かない）。

- 読み手（internal / investor / customer）
- 目的（例: 開発と予算の承認、資金調達、導入の検討）
- 発表時間と枚数の目安（1 枚 1〜2 分が目安）
- 発表で使うか、配布して読んでもらうか（配布なら発表者ノートを厚くする）

### ステップ 2: 材料の読み込みと対応表

§1 の入力を読み、§3 の各章について、使う成果物の節を対応表にまとめる。対応する材料がない章は、省くか、成果物を補うよう案内するかを決める。

### ステップ 3: 構成案の提示と合意

スライドの一覧を示し、承認を得る。

| # | レイアウト | 見出し（主張） | 使う材料 |
|---|---|---|---|
| 1 | title | <題名> | concept |
| 2 | message | <伝えたい 1 文> | project.md §1 |

修正があれば直して再提示する。合意するまで書き出さない。

### ステップ 4: デザインスペックの用意

`docs/presentation/design.yaml` がなければ、[templates/design.yaml](./templates/design.yaml) から作る。次を質問する。

- 会社やブランドの雛形の .pptx があるか（あれば `template` に指定する。雛形の背景とマスターの上に描く）
- ブランドの色（なければテンプレートの色のまま）
- フォント（既定は Meiryo。社内の標準フォントがあればそれにする）

### ステップ 5: slides.md の書き出し

§4 の規約に従って `docs/presentation/<読み手>/slides.md` を書く。

- 各スライドの数字は、成果物の値をそのまま写す。丸める場合は、丸めたことが分かる書き方にする（「約」「〜」）。
- 収支のグラフは `docs/project.md` の計算結果（`plan.py` の出力）から写す。
- 発表者ノートには、スライドに書ききれない説明と根拠を書く。配布用なら、ノートだけで読み手が理解できる程度に書く。

### ステップ 6: 検査

```bash
uv run <skills>/speckit-presentation/scripts/build_pptx.py docs/presentation/<読み手>/slides.md --check
```

`<skills>` は、このスキルが置かれた skills ディレクトリである。uv がない環境では `pip install python-pptx PyYAML` のうえで `python3`（または `python`、`py -3`）で実行する。

エラーは必ず直す。上限を超えた警告は、文を短くする、スライドを分ける、レイアウトを変えるなどして直す。直さない場合は理由を報告に書く。

### ステップ 7: pptx の生成

```bash
uv run <skills>/speckit-presentation/scripts/build_pptx.py docs/presentation/<読み手>/slides.md
```

`docs/presentation/<読み手>/proposal.pptx` ができる。見た目を確かめられる環境（PowerPoint、または日本語フォントの入った LibreOffice で PDF に変換できる環境）なら、文字のあふれや重なりを確かめ、問題があれば `slides.md` か `design.yaml` を直して作り直す。

### ステップ 8: 報告

- 作成・更新したファイル
- スライドの枚数と構成の要約
- 検査の結果（直さなかった警告があれば、その理由）
- 材料が足りずに省いた章と、補うためのスキル（`speckit-project` など）

## 3. 読み手ごとの構成

| 章 | internal（社内の承認） | investor（投資家） | customer（顧客・パートナー） |
|---|---|---|---|
| 表紙と要約 | ◎ 何を承認してほしいか | ◎ 一言で言う事業 | ◎ 何ができるか |
| 課題 | ○ | ◎ 課題の大きさ | ◎ 相手の困りごと |
| 解決策と差別化 | ○ | ◎ 勝ち筋 | ◎ 使うと何が変わるか |
| 市場規模 | △ | ◎ TAM・SAM・SOM | — |
| 機能と MVP の範囲 | ◎ | △ | ○ 使える機能 |
| 価格と収益モデル | ○ | ◎ | ◎ 価格 |
| 収支計画と必要資金 | ◎ 予算と回収 | ◎ 成長と調達額 | — |
| KPI と判断基準 | ◎ 見直し・撤退の基準 | ○ | — |
| スケジュールと体制 | ◎ | ○ チーム | ○ 導入の流れ |
| リスクと対策 | ◎ | ○ | △ セキュリティと運用 |
| 構成と費用 | ○ | △ | △ |
| お願いしたいこと | ◎ 承認の依頼 | ◎ 出資の依頼 | ◎ 次の一歩 |

◎ は厚く（複数枚）、○ は 1 枚、△ は必要なら 1 枚、— は入れない。

## 4. slides.md の規約

- 先頭の front matter に、`title`、`audience`、`purpose`、`duration`、`date`、`author`、`design`（`../design.yaml`）を書く。
- スライドは `---` だけの行で区切る。
- レイアウトは `<!-- layout: <名前> -->` で指定する（省略時は `bullets`）。
- 見出しは `# ` で書く。発表者ノートは `<!-- notes … -->` で書く。出典は `> 出典: …` で書く（スライドの下に小さく入る）。
- 本文中の `**…**` は太字になる。

| レイアウト | 書き方 | 用途 |
|---|---|---|
| `title` | `#` 題名、続く段落が副題 | 表紙 |
| `section` | `#` 章の名前（段落を 1 つ添えてもよい） | 章の扉 |
| `bullets` | `- ` の箇条書き（2 階層まで。下位は 2 字下げ） | 要点の説明 |
| `two-column` | `## ` の小見出しを 2 つ、それぞれの下に箇条書き | 比較（既存の手段と本サービスなど） |
| `table` | Markdown の表（1 行目が見出し） | 機能、価格、スケジュールなど |
| `stats` | `- **数値** 説明` を最大 4 つ | 市場規模、KPI などの数字の強調 |
| `chart` | Markdown の表（1 列目が項目、2 列目以降が系列）と `<!-- chart: column\|bar\|line\|pie -->` | 収支の推移、構成比 |
| `image` | `![説明](images/…)`（slides.md からの相対パス） | 画面のイメージ、構成図 |
| `message` | `#` に 1 文、続く段落が補足 | 要約、お願いしたいこと |

1 枚に収める量の上限は `design.yaml` の `limits` にある。`--check` が、超えた箇所を警告する。

## 5. 更新モード

`slides.md` がすでにある場合は、次のように進める。

1. 成果物の変更（`docs/project.md` の更新履歴など）と、見直しのきっかけを確かめる。
2. 影響を受けるスライドと、変える内容を示し、合意を取る。
3. `slides.md` を直し、§2 のステップ 6 と 7 で検査して作り直す。
4. 別の読み手の版がある場合は、同じ数字を使っているスライドも直すかを確かめる。

## 6. 禁止事項

- 成果物にない数字、目標、価格、事実をスライドに書くこと
- 出典のない数字をスライドに書くこと
- ユーザーの合意なしに `slides.md` や `design.yaml` を書き出す、または上書きすること
- pptx を直接編集して直すこと（`slides.md` と `design.yaml` に反映して作り直す）

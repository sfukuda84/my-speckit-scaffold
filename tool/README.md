# new-speckit-project

[my-speckit-scaffold](https://github.com/sfukuda84/my-speckit-scaffold) から新規プロジェクトを作成し、AI エージェントで立ち上げ（`speckit-bootstrap`）を始めるコマンド。macOS、Linux、Windows で動く（Python 3.9 以上）。

## 導入

```bash
uv tool install "git+https://github.com/sfukuda84/my-speckit-scaffold#subdirectory=tool"
```

更新は `uv tool upgrade new-speckit-project` で行う。

## 使い方

```bash
new-speckit-project <作成先> [-m "コアコンセプト" | --concept-file <ファイル>] [--agent claude|codex|agy|kiro|opencode] [--auto | --oneshot] [--cloud <owner>/<name>]
```

| オプション | 内容 |
|---|---|
| `-m`, `--message` | サービスのコアコンセプト。省略すると対話で入力を受ける |
| `--concept-file` | コアコンセプトを書いたファイル（UTF-8） |
| `--agent` | 立ち上げに使うエージェント（既定: `claude`） |
| `--ref` | scaffold のブランチまたはタグ（既定: `main`。環境変数 `SPECKIT_SCAFFOLD_REF` でも指定できる） |
| `--repo` | scaffold の Git リポジトリ（環境変数 `SPECKIT_SCAFFOLD_REPO` でも指定できる） |
| `--auto` | 立ち上げで質問せず、エージェントの推奨案を採用して進める（`speckit-bootstrap --auto` で起動する） |
| `--oneshot` | 立ち上げの最初に一度だけ、予算や MVP の範囲などをまとめて質問し、以降は自動で進める（`speckit-bootstrap --oneshot` で起動する） |
| `--cloud` | Claude Code のクラウドセッションで立ち上げる。GitHub に `<owner>/<name>` の非公開リポジトリを作り（空の既存リポジトリならそれを使い）、`main` を push してから `claude --cloud` で `speckit-bootstrap` を始める。`gh` とログインが必要。`--agent claude` のときだけ使え、`--auto` / `--oneshot` を省くと `--oneshot` で進める。付けなければ従来どおりローカルで起動する |
| `--no-launch` | エージェントを起動せず、手順の案内だけを表示する（`--cloud` では push までを行う） |

## 作成済みのプロジェクトを更新する

```bash
new-speckit-project update [プロジェクト] [--dry-run] [--ref <ブランチまたはタグ>] [--repo <リポジトリ>]
```

scaffold の持ち物（スキル、Spec Kit のスクリプトとテンプレート、ルール、`MANUAL.md` など）だけを取り込み、1 つのコミットにする。scaffold のどの版とも中身が一致しないファイルは手で直したものとみなして上書きせず、新しい版を `.scaffold-new/` に置く。取り込んだ版は `.specify/scaffold.json` に記録する。

## 開発

```bash
cd tool
uv run --no-project --with python-pptx --with pyyaml python -m unittest discover -s tests
```

テストは、作業ツリーの scaffold を一時的な Git リポジトリにして、そこから作成を試す。worktree 管理のスクリプト、`validate.py`、`plan.py`、`build_pptx.py` のテストも含む（python-pptx がなければ、pptx の生成のテストは飛ばす）。

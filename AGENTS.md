# Project context

作業開始時は、このディレクトリの `active_context.md` を読んで前セッションの状態を確認する。

- このプロジェクトは日本向け Hyundai Bluelink の Home Assistant 統合を開発するための作業場所。
- 対象は日本向け EV。ユーザーが実車確認できるのは IONIQ 5 のみ。水素車は対象外。
- ユーザー向けの表示文言（設定画面、エンティティの表示名、説明、エラーメッセージなど）は基本的に日本語にする。
- 日本版の domain・デバイス識別子・エンティティ識別子は新しく設計してよい。既存版の履歴を引き継ぐための互換処理は不要。
- 隣接する参考実装リポジトリと、この開発用リポジトリを取り違えない。

## Documentation lookup

ライブラリ・フレームワーク・SDK・API・CLI・クラウドサービスの仕様や設定を調べるときは Context7 MCP を優先する。
まず `resolve-library-id` で対象を解決し、続いて `query-docs` に具体的な質問を渡す。索引にない内部 API は、公式資料や実装・取得済みの調査結果で確認する。
単なるリファクタリング、業務ロジックのデバッグ、コードレビュー、一般的なプログラミング概念には不要。

## Agent development kit

`NEXTAltair/altairs-agent-dev-kit` の `v0.6.0` を導入している。skills は `skills-lock.json`、
hook runtime は `.agent-kit/hooks.lock.json` で固定する。
プロジェクト方針とユーザーの指示を kit の汎用例より優先する。

- 作業に関係する `.claude/rules/*.md` を Codex / Claude Code 共通の開発規約として読む。
- アプリの実装・テストを変更する前に `.claude/rules/git-workflow.md` と
  `.agents/skills/worktree-workflow/SKILL.md` を読み、`.agents/worktree/` 配下の専用 worktree で作業する。
  docs / 開発ツール設定だけの変更は kit の例外に従い共有 checkout で行える。
- 既存実装の活用には `check-existing`、検証には `qa-expert`、文書の保守には
  `docs-freshness-audit`、PR 作成後には `pr-maintainer` / `pr-autoloop` を必要に応じて使う。
  skill の実体は `.agents/skills/`、Claude の参照は `.claude/skills/`。
- PySide6 / Qt、SQLAlchemy、GUI テストの設定はこのプロジェクトには適用しない。
  kit のサンプルコマンドを導入済みの構成とみなさず、HA 統合の実装と依存定義に合わせて検証する。
- Python の実行環境は共有 checkout の `.venv` を使う。`UV_PROJECT_ENVIRONMENT` は
  ローカルの `.codex/config.toml` と `.claude/settings.local.json` に設定する。
  依存定義はまだないため、環境作成と依存導入はコード移植時に行う。
- hook のプロジェクト設定は `.claude/hooks/rules/` に置く。Claude / Codex の編集ゲートは
  `src/`、`tests/` に加え `custom_components/` を保護する。
  Codex は `apply_patch` を検査する。Claude は WorktreeCreate / WorktreeRemove も登録し、
  Codex の worktree 作成・削除は上記の作業手順に従う。
- 認証情報と診断の生データは既存の秘密情報の扱いに従う。HA の認証情報の保存方式は
  Config Entry / 再認証の設計に合わせ、kit の環境変数の例で置き換えない。

別の checkout で復元するときは、同じタグの kit から `install.sh --target <repo> --all` を実行する。
Claude の hook 登録は installer が表示する設定を `.claude/settings.json` にマージする。
ローカルの共有 venv 設定もその環境のパスで作る。既存設定がある場合は `.new` の提案を確認し、
固定版を変える意図がなければ `--force` は使わない。Codex の新規 hook は `/hooks` で信頼を確認する。

共有するのは lock、hook 登録と独自設定、共通 rules / agent 定義、worktree 検出用の
VS Code 設定。この固定版から復元できる skills / runtime、worktree、ログ、端末固有の設定と
installer の `.new` 提案は `.gitignore` に置く。

導入設定の検証コマンド（アプリのテストとは別）。`/path/to/kit` は `v0.6.0` を
checkout した kit のパスに置き換える:

```bash
python3 /path/to/kit/scripts/check_config_consistency.py --root .
python3 /path/to/kit/scripts/check_skills_lock.py --root .
```

設定整合 lint は `.claude/settings.json` を検査する。共有 venv の値はローカル設定にあるため、
両クライアントの `UV_PROJECT_ENVIRONMENT` が共有 checkout の `.venv` を指すことも確認する。

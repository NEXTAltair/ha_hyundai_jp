# Git Workflow Rules

Issue解決・機能開発時のブランチ戦略とワークツリー運用ルール。

## 実装作業は worktree から開始(必須)

Issue解決・機能開発・PR準備・複数ファイル実装は、**必ず `.agents/worktree/` 配下の専用 worktree から開始する**。共有 checkout (プロジェクトルート) で実装作業の edit / stage / commit / push / rebase をしない。

### worktree + PR を要さない例外(共有 checkout / メインブランチ直 push 可)

以下は worktree も PR も介さず、共有 checkout で作業しメインブランチへ直接 push してよい(**新規作成・更新の両方**):

- **ドキュメント系(ADR を除く)**: `docs/` 配下、README 等の作成・更新(コード変更を伴わないもの)
- **確定済み ADR のみ**: `docs/decisions/` 等の ADR は **Status=Accepted/Implemented に確定したものに限り** メインブランチ直 push 可。
  **作成中 / Status=Proposed の ADR は worktree+ブランチで隔離し、確定するまでメインブランチに push しない**。
  理由: ADR は"規約そのもの"なので、未確定の draft がメインブランチに乗ると、以降にそこから派生する
  全 worktree がそれを引き継ぎ、別セッションが Status を区別せず「確定済み規約」として従ってしまう(誤誘導事故)。
- **開発ツール周りの chore**: SKILL 定義、プロンプト/コマンド、Agent 定義、hook・ルール・設定、`.gitignore` 等の作成・更新
- read-only 調査、ツール検証、worktree 掃除

判断基準: **アプリのソース (`src/`, `tests/` 等) や schema/migration を触るか**。触るなら worktree + PR、触らない docs/tooling chore なら共有 checkout で直接でよい。**ただし ADR は確定(Accepted/Implemented)まで worktree で隔離する**(上記参照)。

```bash
# 実装着手時の標準手順
git fetch origin
git worktree add .agents/worktree/issue-123 -b fix/issue-123 origin/main
# 以降の編集・コミット・push はこの worktree 内で行う
```

完了の定義(ユーザーが明示的に「publish 前で止めて」「draft のまま」と言わない限り):
1. worktree で実装
2. lint / 型チェック([coding-style.md](coding-style.md) 参照)と CI-equivalent filter([testing.md](testing.md) 参照)で検証
3. commit & push
4. ready-for-review な PR を起票
5. PR 保守自走(CI / bot レビュー)を回し、safe なら squash merge
6. merge 後 worktree を `git worktree remove` で即削除

ローカル実装だけで作業を終えない。PR URL と最終監視状態を成果として報告する。auth / network / 検証失敗 / スコープ不明で PR 起票がブロックされた場合は、黙ってローカル変更で止めず blocker を明示する。

> 注: kit の worktree 作成 hook (`hook_worktree_create.py`) は自動 worktree 作成を仲介する。手動 `git worktree add` も fallback として有効。
> 初期設定 (.gitignore / VS Code 検出設定)、hook にブロックされた後の復帰、並列 worker への割当、merge 後の掃除までの
> 具体的なコマンド手順は `worktree-workflow` skill (導入していれば) に集約している。本ファイルは方針のみを定める。

### PR 保守自走の枠組み

上記手順 5「PR 保守自走」は CI / bot レビュー完了まで `gh` で polling し、必要なら同じ worktree で
修正 commit を積む。枠組みの要点: polling 間隔は数分単位、待機の合計上限は 20 分程度で打ち切って
状況を PR にコメントする。修正ループにも上限 (目安 4 回) を設け、上限に達しても解消しない場合や
同じファイル群でレビュー指摘が連鎖する場合は、局所修正を続けず「設計変更検討」としてエスカレーション
する (PR へ選択肢をコメント + 設計検討 Issue を起票)。自動修正で許可するのはアプリコード・テスト・
ドキュメント・依存更新の範囲に限り、`.github/workflows/**` の変更、権限/secret 設定変更、
メインブランチへの直接 push、Git 履歴改変は自動修正の対象外とし、必要なら実装せずエスカレーションに
切り替える。CI / レビューが blocking な問題を残さず、これらの禁止事項に触れていない場合のみ、
人手を介さず squash merge してよい。詳細な判断基準・polling コマンド例・状態管理方針は
`pr-maintainer` / `pr-autoloop` skill (導入していれば) を参照する。

## ブランチ運用

このセクションは**アプリのソース (`src/`, `tests/` 等)・schema/migration を触る実装作業**に適用する。docs/tooling chore は上の「worktree + PR を要さない例外」が優先され、専用ブランチを切らずメインブランチ直 push してよい。

### メインブランチでの直接作業禁止(アプリコード作業)
- アプリコードの Issue解決・機能開発は必ず専用ブランチ(かつ worktree)で行う
- ブランチ命名: `fix/issue-{番号}`, `feat/issue-{番号}`, `refactor/issue-{番号}`

### ブランチ作成タイミング
- Issueやタスクの実装開始時に作成
- アプリコードに触れる変更は、単純なtypo修正や1行変更でも原則ブランチを切る(docs/tooling chore は例外節に従い不要)

## ワークツリー運用

### 配置先
- **必ず `.agents/worktree/` 配下に作成する**(プロジェクトツリー内に見えるので把握しやすい。kit の hook 群のデフォルト前提でもある)
- プロジェクトルートより上流には作成しない(エクスプローラに出ず見づらい)

```bash
# 正しい
git worktree add .agents/worktree/fix-issue-123 -b fix/issue-123

# 禁止: プロジェクト外(上流)に作成
git worktree add ../fix-issue-123 -b fix/issue-123
```

### Agent呼び出し時
- 実装タスクの Agent は専用 worktree の isolation 機能があればそれを使う。またはリード側で `git worktree add` した専用 worktree のパスを渡す fallback も可
- 並列実装では worker ごとに別 worktree を割り当て、書き込みスコープ(担当ファイル/モジュール)を分離する
- メインワークスペースの作業状態を汚さない

### クリーンアップ
- マージ完了後は、PR 作業で使ったワークツリーを即削除する
- 作業中のカレントディレクトリが削除対象の場合は、共有 checkout に戻ってから削除する
- 複数の残骸をまとめて掃除する場合は、cleanup スクリプト/Makefile ターゲットがあればそれを使う
- cleanup は `.agents/worktree/` 配下に限定し、未コミット変更がなく、merged PR またはメインブランチへ到達済みの worktree だけを削除する対象とする

```bash
git worktree remove .agents/worktree/fix-issue-123
```

> **プロジェクト固有:** cleanup を自動化する Makefile ターゲット (`worktree-cleanup-merged` 等) があれば、ここにコマンドを追記する。

## venv / 実行環境(ワークツリー内)

venv / 実行環境の分離粒度 (worktree 間でどこまで共有・分離するか、package 間でどう扱うか) は [parallel-execution.md](parallel-execution.md) に集約している。ワークツリー内でパッケージマネージャコマンドを実行する場合は、そちらのルールに従う (原則: 専用 venv を作らず共有実行環境を明示する)。

並列で複数の同期系操作を走らせる場合の詳細ルールも [parallel-execution.md](parallel-execution.md) を参照。

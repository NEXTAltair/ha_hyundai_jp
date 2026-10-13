# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

プロジェクト方針（対象車種、識別子の新規設計、Context7 の使い方）は `AGENTS.md`、前セッションの状態と未決事項は `active_context.md` にある。作業前に両方を読む。この文書ではそれらを繰り返さない。

開発手順には `altairs-agent-dev-kit v0.6.0` を使う。適用範囲・復元・検証方法は
`AGENTS.md` の Agent development kit 節、共通規約は `.claude/rules/` を参照する。

## リポジトリの現状

- domain は `hyundai_bluelink_jp`（2026-10-13 確定、#7）。最初の版はモニタリングだけ（#8）。
- 日本向けの通信は `hyundai_kia_connect_api` に入れず、統合の中に持つ（`docs/decisions/0001-jp-api-client-in-integration.md`）。
- GitHub は private リポジトリ `NEXTAltair/ha_hyundai_jp`（remote `origin`）。課題は Issue で管理する。`active_context.md` は `.gitignore` 済みで、ローカルにだけある。
- コードは参考実装 `/home/altair/src/ha_kia_hyundai_USA-jp-reference`（旧 fork の `v3.3.3-jp.2`、本番でモニタリング動作確認済み）から必要な部分を移す。参考実装5件は `~/code-workspace/ha_hyundai_jp.code-workspace` のフォルダーと同じで、`.claude/settings.local.json` の `additionalDirectories` から読める（Edit/Write は deny 済み）。用途と取得元は `active_context.md` を参照。参考実装は読むだけにして変更しない。
- 旧作業場所 `/home/altair/src/ha_kia_hyundai_USA` は reset や広範囲の `git add` をしない。未コミットの記録と `local-private/` がある。

## コマンド

Python 3.14。依存は `uv` で管理する（`pyproject.toml` と `uv.lock`）。テストの HA の版は `pytest-homeassistant-custom-component` が固定する。実機での確認は、HA が配布している HA Core 最新版の Docker イメージで行う（2026-10-13 決定）。

```bash
uv sync                                          # 共有 .venv に依存を入れる。並列に実行しない
uv run pytest -q                                 # 全テスト
uv run pytest tests/test_client.py -q            # 単一ファイル
uv run pytest tests/test_status.py -k <name> -q  # 単一テスト
uv run ruff check . && uv run ruff format --check .
uv run mypy custom_components
```

CI（`.github/workflows/ci.yml`）は Ruff、mypy、pytest、Hassfest、HACS validation を実行する。テストは localhost のモックサーバーと合成データを使い、実車や実サーバーには接続しない。

## アーキテクチャ

`custom_components/hyundai_bluelink_jp/` の構成:

- `api/`: HA に依存しない日本向けクライアント。
  - `client.py`: ログイン、車両一覧、端末登録、CCS2 の状態取得。失敗は `errors.py` の例外にし、空の状態で隠さない。
  - `status.py`: 応答を `VehicleStatus` に読み取る。距離は km、割合は小数のまま。欠けた値は None にし、推測で埋めない。
  - `const.py`: 接続先、client secret、APP_ID、CFB（アプリ共通の定数、#5）。
- `coordinator.py`: アカウントの全車両を10分ごとに取得する。取得の失敗は `UpdateFailed`（エンティティは unavailable）、パスワードの誤りは `ConfigEntryAuthFailed`（再認証）。HA の取得成功時刻を `fetched_at` に持つ。
- `sensor.py` / `binary_sensor.py` / `device_tracker.py`: 車両ごとのエンティティ。unique_id は `{carId}_{key}`、表示名は `translations/` の ja / en。
- `diagnostics.py`: アカウント情報、トークン、識別子、位置を伏せる。

旧日本版（参考実装の `kia_hyundai_api/jp_hyundai.py`）から引き継いだ手順: ログイン前にセッション言語を日本語にする（失敗したら資格情報を送らない）、端末登録は Authorization なしで行い結果をキャッシュする、`resCode: 4002` なら登録し直して1回だけ再試行する。

旧日本版から変えた点: CCS2 だけを使い、HTTP 404 は未対応車両として失敗にする（legacy `/status/latest` は持たない）。Stamp サーバー、PIN、操作系の試作は持たない。旧版の操作系や legacy 解析を参照するときは参考実装を読む。参考実装には実車の状態を読むだけの確認用スクリプト `scripts/jp_status_probe.py` もある。

## 守ること

- 実車への操作コマンド（施錠、空調、充電など）は、ユーザーの明示的な指示なしに送らない。操作 API は日本版公式アプリで確認し、韓国版や米国版のリクエストが通ると仮定しない。
- 漏らしてはいけないのは、ユーザーの Bluelink アカウントのメールアドレスとパスワード、遠隔操作の PIN、それと同じように使えるログイン後のトークンや cookie。チャット、ログ、commit に出さない。HA 診断ファイルにはこれらが含まれ得るので、生データを出す前に確認する。
- CFB と OAuth client secret は秘密ではない。海外仕様（`KiaUvoApiEU.py` など）と同じくコードに定数として埋め込む（2026-10-13 決定、#5）ので、チャットに出してよい。値は `custom_components/hyundai_bluelink_jp/api/const.py` にある。
- 実車で確認できるのは日本版 IONIQ 5 のみ。他車種を対応済みとして扱わない。
- HACS はリリースタグを参照する。マージしただけでは配布されないので、リリースの公開まで考える。

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

プロジェクト方針（対象車種、識別子の新規設計、Context7 の使い方）は `AGENTS.md`、前セッションの状態と未決事項は `active_context.md` にある。作業前に両方を読む。この文書ではそれらを繰り返さない。

開発手順には `altairs-agent-dev-kit v0.6.0` を使う。適用範囲・復元・検証方法は
`AGENTS.md` の Agent development kit 節、共通規約は `.claude/rules/` を参照する。

## リポジトリの現状

- アプリケーションコードはまだない。domain は `hyundai_bluelink_jp`（2026-10-13 確定、#7）。
- 日本向けの通信は `hyundai_kia_connect_api` に入れず、統合の中に持つ（`docs/decisions/0001-jp-api-client-in-integration.md`）。
- GitHub は private リポジトリ `NEXTAltair/ha_hyundai_jp`（remote `origin`）。課題は Issue で管理する。`active_context.md` は `.gitignore` 済みで、ローカルにだけある。
- コードは参考実装 `/home/altair/src/ha_kia_hyundai_USA-jp-reference`（旧 fork の `v3.3.3-jp.2`、本番でモニタリング動作確認済み）から必要な部分を移す。参考実装5件は `~/code-workspace/ha_hyundai_jp.code-workspace` のフォルダーと同じで、`.claude/settings.local.json` の `additionalDirectories` から読める（Edit/Write は deny 済み）。用途と取得元は `active_context.md` を参照。参考実装は読むだけにして変更しない。
- 旧作業場所 `/home/altair/src/ha_kia_hyundai_USA` は reset や広範囲の `git add` をしない。未コミットの記録と `local-private/` がある。

## コマンド（参考実装の構成。移植後に合わせて更新する）

Python 3.12、テスト環境は Home Assistant 2025.1.4 に固定（`pytest-homeassistant-custom-component==0.13.205`）。新しい日本版では HA 2025.1.4 の固定を引き継がない。HA が配布している HA Core 最新版の Docker イメージで動作を確認する（2026-10-13 決定）。

```bash
python3 -m pip install -r requirements-test.txt
python3 -m pytest -q                                   # 全テスト（asyncio_mode=auto、testpaths=tests）
python3 -m pytest tests/test_jp_status.py -q           # 単一ファイル
python3 -m pytest tests/test_jp_api.py -k <name> -q    # 単一テスト
python3 -m ruff check .
```

CI は Ruff、pytest、Hassfest、HACS validation を実行する。テストは localhost のモックサーバーと合成フィクスチャを使い、実車や実サーバーには接続しない。

実車を使う確認用スクリプト（`uv run` で実行、秘密値は `local-private/` に置く）:

- `scripts/jp_status_probe.py --cfb-file local-private/jp-stamp-config.json`: キャッシュ済み状態を読むだけ。車両を起こさず、操作コマンドも送らない。出力 `/tmp/jp-status.redacted.json` は共有前に中身を確認する。
- `scripts/jp_stamp_setup.py`: Android エミュレーターと Frida で公式アプリから CFB を一度だけ取得する初期設定用。

## 参考実装のアーキテクチャ（JP 部分）

参考実装は US 版統合に JP を brand `jp_hyundai` として追加した構成。新リポジトリでは US 部分を持ち込む必要はない。

- `config_flow.py`: `async_step_jp_credentials` でメール・パスワード・OAuth client secret を受け取る。CFB 署名データは Options で設定し、保存時にエントリを再読み込みする。再認証でも CFB は保持する。
- `kia_hyundai_api/jp_hyundai.py` の `JpHyundai`: 認証から状態取得までを担う。
  - ログイン前にセッション言語を日本語に設定する。失敗した場合はログインを中止する。
  - 車両一覧は `/api/v1/user/cars`。
  - Stamp は CFB（47 バイトの XOR マスク）と10桁の Unix 時刻から HA 内で生成する。CFB があれば旧 Stamp サーバー URL より優先し、外部サービスへは送らない。経緯は参考実装の `docs/adr/0001-jp-local-stamp.md`。
  - 端末登録 `/api/v1/spa/notifications/register` は Authorization なしで行い、結果を再起動までキャッシュする。`resCode: 4002` で拒否されたら登録を破棄し、登録し直して1回だけ再試行する。
  - 状態取得は CCS2 `/api/v1/spa/vehicles/{id}/ccs2/carstatus/latest` を先に試す。legacy `/status/latest` へ切り替えるのは HTTP 404 のときだけ。
- `kia_hyundai_api/jp_status.py` の `normalize_status`: JP の応答を US 版コーディネーターが期待する dict の形に変換する。JP の時刻は `YYYYMMDDHHmmss.SSS`。既存センサーがマイル前提のため km を変換している（US 版由来の制約）。
- `vehicle_coordinator.py` と各プラットフォームは US 版と共通。JP の操作系（空調、充電、強制更新）は未実装、施錠・解錠は未検証の試作。`check_last_action_finished()` は常に `True` を返す。
- `diagnostics.py`: 状態を `stamp_not_configured` / `device_registration_failed` / `gateway_rejected` / `unsupported_response` などに分類する。資格情報、メールを含むタイトル、座標は伏せる。

## 守ること

- 実車への操作コマンド（施錠、空調、充電など）は、ユーザーの明示的な指示なしに送らない。操作 API は日本版公式アプリで確認し、韓国版や米国版のリクエストが通ると仮定しない。
- 漏らしてはいけないのは、ユーザーの Bluelink アカウントのメールアドレスとパスワード、遠隔操作の PIN、それと同じように使えるログイン後のトークンや cookie。チャット、ログ、commit に出さない。HA 診断ファイルにはこれらが含まれ得るので、生データを出す前に確認する。
- CFB と OAuth client secret は秘密ではない。海外仕様（`KiaUvoApiEU.py` など）と同じくコードに定数として埋め込む（2026-10-13 決定、#5）ので、チャットに出してよい。CFB の値は `/home/altair/src/ha_kia_hyundai_USA/local-private/jp-stamp-config.json` にある。
- 実車で確認できるのは日本版 IONIQ 5 のみ。他車種を対応済みとして扱わない。
- HACS はリリースタグを参照する。マージしただけでは配布されないので、リリースの公開まで考える。

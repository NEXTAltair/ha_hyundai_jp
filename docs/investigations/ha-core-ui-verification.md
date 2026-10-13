---
type: Experiment
title: 公式 HA Core コンテナでの画面・モニタリング検証
description: 専用コンテナの起動、日本語の設定画面、入力検証を確認。実データのモニタリングはログイン待ち。
timestamp: 2026-10-13
status: active
tags: [home-assistant, docker, qa, monitoring]
---

# 公式 HA Core コンテナでの画面・モニタリング検証

ユーザー指定の対象は HA の画面・設定・モニタリング。実車への遠隔操作は対象外。
新しい統合の設定画面まで確認した。Bluelink アカウントがまだ設定されていないため、
車両データの取得・表示を検証済みとは扱わない。

## 環境

| 項目 | 値 |
| --- | --- |
| 検証コード | `bafb8e039e39ee0e1258332cca7bedc54f4622b0`（PR #9 マージ後） |
| 統合 | `hyundai_bluelink_jp` / `0.1.0` |
| HA Core | `2026.10.1`。コンテナ内の `python -m homeassistant --version` で確認 |
| 取得元 | 公式 `ghcr.io/home-assistant/home-assistant:stable` |
| 固定した image digest | `sha256:130241f28d01fa80dfa3b44f7d89781c188d8642ecab9024f079f19f9f82baa0` |
| 実行環境 | Docker Desktop 4.94.0、Engine 29.8.2、Linux/amd64、WSL2 |
| ブラウザ | Playwright 1.63.0、同梱 Chromium、headless、1440 × 1000、`ja-JP` |
| URL | `http://localhost:18123` |
| コンテナ | `hyundai-bluelink-jp-ha-test` |
| 設定 volume | `hyundai-bluelink-jp-test-config` |
| 公開ポート | `127.0.0.1:18123` → コンテナ `8123` |
| 自動再起動 | なし（検証後もコンテナを残し、手動で起動・停止できる） |

`stable` を pull した時点の最新安定版は [2026.10.1](https://github.com/home-assistant/core/releases/tag/2026.10.1)。
実行には取得した digest を指定した。コンテナ内の統合の Python/JSON 全18ファイルは、
マージ済みコードと SHA-256 が一致した。
既存の別用途 HA コンテナの設定・イメージ・実行状態は変更していない。

この結果の対象は Docker Desktop 上の Web UI とクラウド統合である。
ローカル機器の探索・Bluetooth・USB 連携、本番環境での動作は検証範囲に含まない。
公式の構成例は [HA Container 導入資料](https://www.home-assistant.io/installation/linux/#install-home-assistant-container)、
ポート制限は [Docker の port publishing](https://docs.docker.com/engine/network/port-publishing/) を参照した。

## 実行結果

| ケース | 手順と期待結果 | 結果 |
| --- | --- | --- |
| 起動 | 公式イメージを起動し、ブラウザで初期設定へ進める | 成功 |
| 初期設定 | 検証専用の管理者を作成し、日本語・日本・JST・メートル法で完了する | 成功 |
| 統合選択 | 設定 → デバイスとサービス → 統合を追加で名称を検索する | 成功。Hyundai Bluelink Japan が表示される |
| 設定画面 | 日本語の説明とメールアドレス・パスワードだけを表示する | 成功。CFB、client secret、PIN の入力なし |
| 入力型 | メール欄が email、パスワード欄が password で、両方必須である | 成功。DOM の型と必須属性を確認 |
| 空欄 | 空欄のまま送信し、バックエンドへ入力を送らない | 成功 |
| メール形式 | `invalid-address` をメール欄へ入れ、形式エラーで送信を止める | 未達。下記の指摘を参照 |
| キャンセル | 設定ダイアログを閉じる | 成功。設定エントリーを作成しない |
| 起動ログ | Core の ERROR/CRITICAL を確認する | 0件。未検証 custom integration の通常の警告あり |
| 実アカウントの設定 | Bluelink へログインし、設定エントリーが loaded になる | 未実施・入力待ち |
| 車両とセンサー | 車両、センサー、日本語名、距離 km、SOC の値、位置の有無を確認する | 未実施 |
| データ鮮度 | 車両の最終同期と HA の最終取得を区別し、10分後の定期取得を確認する | 未実施 |
| 再読み込み | 統合の再読み込み後、車両状態が復帰する | 未実施 |
| 診断 | 診断を取得し、アカウント情報・トークン・識別子・位置の伏字を確認する | 未実施 |

ブラウザでは初回の画面遷移で `Object`、一度のダイアログ終了で `disconnected` の
pageerror が記録された。後続の設定画面・入力検証・状態照会では再現せず、
対応する Core エラーもなかった。原因の特定はしていない。

## 入力検証の指摘

メール入力は `type=email` で、`invalid-address` に対して DOM の
`validity.typeMismatch` が true になる。それでも送信操作で、
メール・パスワードを含む config flow の継続 POST が発生することを二度確認した。
空欄の送信は止まる。

検証用ブラウザの request interception で、この POST は HA バックエンドへ到達する前に遮断した。
ダミーの資格情報を Bluelink に送信していない。
正しいメールアドレスでの設定に支障があるとは確認できていない。
今回アプリコードは変更せず、形式チェックを config flow 側でも行うかを後続の判断とする。

## 入力待ちと再開方法

旧作業場所の保存済み診断からは、利用可能なメールアドレス・パスワードを取得できなかった。
ユーザーには検証 HA 上での入力を依頼している。資格情報をチャットへ書く必要はない。

検証用管理者の情報は、Git 管理外の
`local-private/ha-core-test/admin-credentials.json` に権限600で保存した。
操作補助スクリプト、空欄の設定画面のスクリーンショット、ブラウザの専用プロファイルも
同ディレクトリに置き、リポジトリには含めていない。
Bluelink の設定後は専用 Docker volume に Config Entry が保存される。

入力後は、既存のログイン済みブラウザの接続からエントリー状態と登録エンティティを確認し、
値と単位・二種類の時刻・再読み込み・定期取得・診断の検証を続ける。
アカウント情報や座標、車両識別子を検証ログへ出さない。

この端末の WSL 側 Docker ソケットは未構成だったため、Windows 側の Docker CLI を使用した。
Windows の PowerShell では `docker stop hyundai-bluelink-jp-ha-test` で停止し、
`docker start hyundai-bluelink-jp-ha-test` で再開できる。

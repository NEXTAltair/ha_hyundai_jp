---
type: ADR
title: 日本向けの通信は共通ライブラリに入れず統合内に持つ
description: hyundai_kia_connect_api への日本専用クラス追加を見送り、旧日本版の aiohttp クライアントを統合へ移す。
tags: [bluelink, japan, api, home-assistant]
timestamp: 2026-10-13
status: accepted
---

# 日本向けの通信は共通ライブラリに入れず統合内に持つ

## 背景

[Issue #6](https://github.com/NEXTAltair/ha_hyundai_jp/issues/6) で、`hyundai_kia_connect_api` に
日本向けの対応を追加できるかを調べた（[調査結果](../investigations/jp-api-library-fit.md)）。
調査は、同期 `requests` を維持して日本専用の `ApiImplType1` 派生クラスを追加し、
HA から executor 経由で呼ぶ案を推奨した。

ユーザーの条件は「軽微な変更で済むなら上流へ PR を出す」だった。調査の概算は
日本クラス、テスト、fixture を合わせて約 700〜1,200 行で、軽微な変更には当たらない。
また、上流がマージしてリリースするまで、新しい統合はその変更に依存して配布できない。

## 決定

ユーザーの判断で、共通ライブラリへ日本専用クラスを追加する案は見送る。

日本向けの認証、端末登録、状態取得、応答の正規化は、この統合の中に持つ。
実装は、本番でモニタリングの動作を確認している旧日本版（`ha_kia_hyundai_USA` の
`v3.3.3-jp.2`、`kia_hyundai_api/jp_hyundai.py` と `jp_status.py`）の `aiohttp` クライアントを移す。
通信は HA の `aiohttp` ヘルパーで得たセッションで行い、executor は使わない。
ログインは cookie に依存するので、他の統合と cookie を共有しないセッションにするかは移植時に決める。

## 結果

- 上流のリリースを待たずに配布できる。
- 日本向けの通信と解析は、この統合で保守する。
- 旧版の米国版統合に合わせた制約（マイル換算、米国版コーディネーターの dict 形式）は引き継がない。
- 調査で見つかった注意点（精度、日時の欠落、任意項目の欠落、最終取得試行と最終取得成功の区別）は、
  移植時の確認項目として使う。
- 共通ライブラリへの日本対応の追加は、行う場合も新しい判断として扱う。

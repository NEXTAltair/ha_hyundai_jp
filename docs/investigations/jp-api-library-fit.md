---
type: Investigation
title: 共通 API ライブラリへの日本対応追加の評価
description: 同期 requests と日本専用クラスを使う案の再利用範囲、差分、検証条件。
timestamp: 2026-10-13
status: active
tags: [bluelink, japan, api, home-assistant]
---

# 共通 API ライブラリへの日本対応追加の評価

[Issue #6](https://github.com/NEXTAltair/ha_hyundai_jp/issues/6) の先行実装調査。
本書の推奨は実装・実車確認前の評価であり、採用を確定する ADR ではない。

## 結論

`hyundai_kia_connect_api` の同期 `requests` を維持し、日本専用の
`ApiImplType1` 派生クラスを追加する案を推奨する。HA 側の通信は
`hass.async_add_executor_job` で実行する。既存の `kia_uvo` が認証・トークン更新・
ポーリングに使っている構成で、HA の公式資料にも同じ呼び出し方法がある。

ただし、定数とリージョンを追加するだけでは足りない。日本独自の認証・車両一覧・
再試行制御と、共通 parser の欠落値処理への対応が必要である。
他地域への変更を小さく保てる見込みはあるが、「軽微」と断定するにはモックによる試作が必要。

| 候補 | 評価 |
| --- | --- |
| 同期ライブラリへ日本専用クラスを追加 | 第一候補。Stamp、CCS2 解析、Vehicle を再利用し、上流貢献の希望にも合う |
| 動作確認済みの旧 `aiohttp` クライアントを独立させる | 代替案。共有コードの大幅な改変が必要になった場合に再評価する。日本向け通信・解析の保守は自前になる |
| 共通ライブラリ全体を非同期化する | 今回は推奨しない。他地域と全利用者への変更範囲が大きい |

HA の非同期依存要件は Integration Quality Scale の Platinum 項目である。
同期通信を executor に移す構成を初回リリースで利用する妨げとは判断しない。
根拠: [HA の blocking I/O 対応](https://developers.home-assistant.io/docs/asyncio_blocking_operations/)、
[async-dependency](https://developers.home-assistant.io/docs/core/integration-quality-scale/rules/async-dependency/)、
[kia_uvo coordinator](https://github.com/Hyundai-Kia-Connect/kia_uvo/blob/25e1c76a52bd9f6181082ff5a01b8b426e978cba/custom_components/kia_uvo/coordinator.py)、
[認証処理](https://github.com/Hyundai-Kia-Connect/kia_uvo/blob/25e1c76a52bd9f6181082ff5a01b8b426e978cba/custom_components/kia_uvo/config_flow.py)。

## 前提と調査対象

- 対象は日本向け EV。実車で確認できるのは IONIQ 5 のみ。
- 初回はモニタリングを対象とする。操作 API はリリース後に別途扱う。
- CFB と OAuth client secret はアプリ共通の定数として保持する。アカウント情報・PIN・トークン・cookie は記録しない。
- 実サーバーでの状態取得は別途ユーザー指示が必要。上流 PR の提出前にも確認する。
- 参照クローンは変更せず、実装時は別の fork/開発 checkout を用意する。

| 対象 | 確認した revision | 用途 |
| --- | --- | --- |
| `Hyundai-Kia-Connect/hyundai_kia_connect_api` | `01c851fa4ee25bbf7a15b5075a1c1007e3b38764` / `v4.35.2` | 共通ライブラリ |
| `Hyundai-Kia-Connect/kia_uvo` | `25e1c76a52bd9f6181082ff5a01b8b426e978cba` | 同期 API を利用する HA 統合 |
| `NEXTAltair/ha_kia_hyundai_USA` | `a1c03e54dca76c82594bdf92301162d862ce5c0a` / `v3.3.3-jp.2` | 動作確認済みの日本版クライアント |
| `fregmented/hass-bluelink-kr` | `1eec785` | HA 共有 aiohttp セッションの利用例。韓国の公開 API 向けで、日本の内部 API の代替にはならない |

共通ライブラリと `kia_uvo` は GitHub API でもブランチ先端との一致を確認した。
Context7 で HA 開発資料を取得した。共通ライブラリは検索名を変えても索引で見つからず、
上流ソース・貢献規約・CI を一次資料にした。
上流 Issue/PR の `Japan` と `hyundaijapan` 検索は該当なしだったが、同時開発がない保証にはしない。

## 再利用できる部分と日本向け差分

| 項目 | 再利用・追加の方針 |
| --- | --- |
| HTTP | `ApiImplSession` を利用。既定の接続/読取 timeout は 10/30 秒。包括的な自動 retry は持たない |
| Stamp | `APP_ID` と CFB の XOR 生成を再利用。日本の既知時刻で旧実装と一致を検証する |
| 認証 | 日本のホスト、OAuth フロー、ログイン前の日本語設定を専用実装にする |
| トークン | 共通 Token/Manager に合わせる。共有 refresh-token grant は日本で未確認なので、初回は旧版同様の再ログインを明示する |
| 車両一覧 | `/api/v1/user/cars` と識別子の変換を専用実装にする |
| 端末登録 | `/api/v1/spa/notifications/register` の共通処理を参考に、日本のヘッダー・応答処理を保持する |
| 状態取得 | CCS2 を優先。HTTP 404 のときだけ legacy へ切り替え、4002 のときだけ端末再登録後に一度再試行する |
| データモデル | Vehicle と CCS2 parser を再利用し、日本の値・欠落・未確定値の扱いを補う |
| 操作 | 継承した未対応操作を明示拒否する。UI の非表示だけに依存しない |

共通ライブラリは海外向けの強制更新・施錠・空調・充電などを実装しており、
`ApiImplType1` の window/valet 対応フラグも有効である。日本で使えることは未確認なので、
日本クラスで未対応メソッドを拒否し、能力フラグを無効化する必要がある。
HA のポーリングはキャッシュ取得だけを呼び、`kia_uvo` の自動強制更新分岐をそのまま移植しない。

4002 は文字列/数値の応答コードを正規化し、再登録後も拒否された場合は端末キャッシュを無効化する。
共有 retry decorator を呼ぶだけでは、旧日本版の最終失敗時の無効化まで一致しない。
legacy 応答は `vehicleStatusInfo.vehicleStatus` と外側の odometer・位置を
共有 parser の入力へ組み替える必要がある。端末登録の共有 debug ログは要求・応答全体を出すため、
移植時に端末IDや認証に使える値がログへ残らないことも確認する。

根拠: [ApiImplType1](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api/blob/01c851fa4ee25bbf7a15b5075a1c1007e3b38764/hyundai_kia_connect_api/ApiImplType1.py)、
[ApiImplSession](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api/blob/01c851fa4ee25bbf7a15b5075a1c1007e3b38764/hyundai_kia_connect_api/ApiImpl.py)、
[旧日本クライアント](https://github.com/NEXTAltair/ha_kia_hyundai_USA/blob/a1c03e54dca76c82594bdf92301162d862ce5c0a/custom_components/ha_kia_hyundai/kia_hyundai_api/jp_hyundai.py)。

## 精度・欠落値の確認

旧日本版の synthetic fixture と、共通ライブラリの `const.py`、`utils.py`、`Vehicle.py` の実コード、
AST で抽出した `_update_vehicle_properties_ccs2()` を用いて探索的プローブを行った。
相対 import を除外し、API オブジェクトは `data_timezone` を持つ代替オブジェクトにした。
ライブラリ全体をインストールした通常のテストや通信経路の検証ではない。

| 入力・条件 | 確認結果・必要な対応 |
| --- | --- |
| 距離 `10908.5 km`、航続距離 `601.5 km`、駆動 SOC `99.5` | 値と km を保持。旧 US 互換形式のマイル変換を挟む必要はない |
| 12V SOC `99.5` | `normalize_battery_soc` によって `99` になる。駆動 SOC と同じ精度保持とは言えない |
| CCS2 の同期日時 | `Date` を UTC として読み、01:00 UTC → 10:00 JST に変換。小数秒付き入力も秒精度で解析できる |
| 同期日時の欠落 | parser が現在時刻を代入する。日本版では取得成功時刻と混同せず unknown として扱う必要がある |
| `DTE.Total` の欠落 | `TypeError` が起きる入力がある。任意項目の欠落で全更新が落ちないようにする |
| 信頼性・ロック状態の文字列、タイヤ警告の欠落 | 数値/文字列の差や欠落が有効値に見えるケースがある。旧日本版で確認済みの正規化と unknown の扱いを保持する |

Vehicle は `last_scanned_at` と `last_updated_at` の両方を持つが、
Manager は通信前に `last_scanned_at` を更新する。この値は最終取得試行であり、
HA の「最終取得成功」センサーへそのまま使わない。
駆動 SOC は小数を保持する一方、モデルの型注釈は整数なので整合性も確認する。
legacy の `status.time` は地域時間として読むため、日本クラスに `Asia/Tokyo` を設定する。
CCS2 と legacy の時刻を一律に JST 入力として処理しない。不正日時も回帰テストに含める。

根拠: [Vehicle](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api/blob/01c851fa4ee25bbf7a15b5075a1c1007e3b38764/hyundai_kia_connect_api/Vehicle.py)、
[VehicleManager](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api/blob/01c851fa4ee25bbf7a15b5075a1c1007e3b38764/hyundai_kia_connect_api/VehicleManager.py)、
[utils](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api/blob/01c851fa4ee25bbf7a15b5075a1c1007e3b38764/hyundai_kia_connect_api/utils.py)。

## 上流の開発・検証条件

- MIT ライセンス。旧日本版も MIT。移植部分の著作権・ライセンス表示を維持する。
- Python は `>=3.12`。CI は 3.12 / 3.13 / 3.14 で `pip install -e .[image] pytest syrupy` の後に `pytest` を実行する。
- pre-commit は Ruff lint/format、codespell、基本ファイル検査、pyupgrade、YAML/Prettier、mypy などを設定している。アプリ側キットの設定を上流に持ち込まない。
- CONTRIBUTING はテスト・README 更新・全対応 Python での成功を求める。認証情報が必要との記述もあるが、確認した現行テストにはモックがあり、旧ログイン例は文字列で無効化されている。文書だけを根拠に認証情報を CI に投入しない。
- `requirements.txt` は requests、beautifulsoup4、certifi、tzdata、pycryptodome。画像 extras は CI 用の既存構成で、日本のモニタリングが画像依存を必要とするという意味ではない。
- 新 HA 統合の動作確認はユーザー指定どおり最新の公式 HA Core Docker イメージで行い、旧版の HA 2025.1.4 固定を引き継がない。

根拠: [CONTRIBUTING](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api/blob/01c851fa4ee25bbf7a15b5075a1c1007e3b38764/CONTRIBUTING.rst)、
[CI](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api/blob/01c851fa4ee25bbf7a15b5075a1c1007e3b38764/.github/workflows/python-tests.yml)、
[pre-commit](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api/blob/01c851fa4ee25bbf7a15b5075a1c1007e3b38764/.pre-commit-config.yaml)、
[setup.py](https://github.com/Hyundai-Kia-Connect/hyundai_kia_connect_api/blob/01c851fa4ee25bbf7a15b5075a1c1007e3b38764/setup.py)。

## 試作の範囲と採用条件

変更の中心は日本クラスの新設、`const.py` の日本リージョン登録、
`VehicleManager.py` の生成分岐、README、合成 fixture と回帰テスト。
共通 parser の全地域向け改修は別途判断し、日本対応に無関係な修正を混ぜない。

概算は、日本クラス 300〜500 行、地域登録・生成分岐 10〜20 行、
JP テスト 3〜4 ファイルと合成 fixture 400〜650 行、文書数十行。
合計約 700〜1,200 行と文書を見込む。実装前の概算であり、HA 側とライブ検証は含まない。
共有モデルの SOC 型注釈も数行の修正候補になる。

1. モックで日本の認証・日本語設定・車両一覧・端末登録・状態取得を通す。
2. 404 以外では legacy に切り替えず、4002 再試行が一度に収まることを検証する。
3. Stamp、距離、駆動 SOC、日時と欠落値を旧合成 fixture から回帰テストにする。
4. 未対応のすべての公開操作経路が HTTP 送信前に拒否されることを検証する。
5. 既存地域の回帰テストを通す。広範な共通実装変更が必要なら、aiohttp 独立案を再評価する。
6. HA の設定・再認証・ポーリングを executor に通し、通信エラーは UpdateFailed、認証エラーは ConfigEntryAuthFailed に分類する。取得成功時刻は成功時だけ更新する。

次の作業は、この境界を確認するモック試作。上流 PR を出す前には、具体的な差分と検証結果をそろえてユーザーに確認する。

## 未検証・後続事項

- 同期化した日本の認証・再認証・token 寿命は未検証。旧非同期クライアントの稼働実績を移植後の成功とみなさない。
- API 回数制限、他車種、操作 API、上流メンテナーの受入判断は未確認。
- `SoH`、容量、電費などの意味の検証とエンティティ採否は Issue #3 で扱う。
- 新 domain と表示名は Issue #7 で未確定のまま。
- 本調査で実車・実サーバーへの接続、アプリ実装、fork 作成、上流 PR 提出は行っていない。

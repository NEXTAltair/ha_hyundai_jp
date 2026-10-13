# Index

* [日本向けの通信は共通ライブラリに入れず統合内に持つ](decisions/0001-jp-api-client-in-integration.md) — hyundai_kia_connect_api への日本専用クラス追加を見送り、旧日本版の aiohttp クライアントを統合へ移す。
* [共通 API ライブラリへの日本対応追加の評価](investigations/jp-api-library-fit.md) — 同期 requests と日本専用クラスを使う案の再利用範囲、差分、検証条件。この案は採用を見送った（ADR 0001）。

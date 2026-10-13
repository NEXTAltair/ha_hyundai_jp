"""日本向け Bluelink の接続先と、公式アプリ共通の定数。"""

API_HOST = "ccs-apigw.hyundaijapan.com:8080"
USER_API_URL = f"https://{API_HOST}/api/v1/user/"
SPA_API_URL = f"https://{API_HOST}/api/v1/spa/"

# 公式アプリの OAuth client。client secret はアプリに埋め込まれた全利用者共通の値で、
# 海外向けの実装と同じくコードに持つ（Issue #5）。
CLIENT_ID = "e084c0e4-fcfe-47e3-99c9-36eb93593737"
CLIENT_SECRET = "1Yqexvx7MlbKw6aAobMEl2jAQoA0mQXrWQ5IjHOO7O4YDtdG"  # noqa: S105  # アプリ共通の値（Issue #5）

# ccsp-application-id。日本の Android アプリ 1.0.17 で確認した値。
APP_ID = "8be122e0-b0d9-40b5-a46e-67b25194ba88"
# Stamp を作る 47 バイトの XOR マスク（base64）。APP_ID と対になる。
CFB = "yGeH2vkxepxXpBulEUnI04QXO3CM9oT4E20p+AB8lqHuRZmVEfdQlJmzBX5z5pk="

USER_AGENT = "okhttp/3.12.0"

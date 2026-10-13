"""日本向け Hyundai Bluelink 統合の定数。"""

from datetime import timedelta

DOMAIN = "hyundai_bluelink_jp"
MANUFACTURER = "Hyundai"
DEFAULT_TITLE = "Hyundai Bluelink Japan"

# サーバーのキャッシュを読む間隔。車を起こさないので、値が変わるのは車がクラウドへ同期したときだけ。
UPDATE_INTERVAL = timedelta(minutes=10)

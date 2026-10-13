"""日本向け Bluelink との通信で起きる失敗。"""


class BluelinkError(Exception):
    """日本向け Bluelink との通信の失敗。

    Attributes:
        reason: 診断に残す失敗の分類。
        http_status: 失敗した応答の HTTP ステータス。
        res_code: 失敗した応答の resCode。
    """

    reason = "communication_error"

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        res_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.res_code = res_code


class AuthenticationError(BluelinkError):
    """メールアドレスかパスワードが受け付けられなかった。"""

    reason = "invalid_auth"


class AccountLockedError(BluelinkError):
    """サインインの失敗が続き、アカウントが一時的にロックされた。"""

    reason = "account_locked"


class RequestFailedError(BluelinkError):
    """サーバーが成功以外の HTTP ステータスを返した。"""

    reason = "http_error"


class GatewayRejectedError(RequestFailedError):
    """ゲートウェイが端末の認証ヘッダーを拒否した（HTTP 403）。"""

    reason = "gateway_rejected"


class ApiError(BluelinkError):
    """HTTP は成功したが、応答の retCode が失敗を示した。"""

    reason = "api_error"


class DeviceRegistrationError(BluelinkError):
    """状態取得に必要な端末登録に失敗した。"""

    reason = "device_registration_failed"


class UnsupportedVehicleError(BluelinkError):
    """車両が CCS2 の状態取得に対応していない（HTTP 404）。"""

    reason = "unsupported_vehicle"


class UnsupportedResponseError(BluelinkError):
    """応答の形が想定と違う。"""

    reason = "unsupported_response"

"""日本向け Bluelink の API クライアント。

ログイン、車両一覧、端末登録、CCS2 のキャッシュ済み状態の取得だけを行う。
車を起こす強制更新と遠隔操作は持たない（Issue #4）。
手順は旧日本版（ha_kia_hyundai_USA v3.3.3-jp.2）で本番確認したものを移した。
"""

import base64
import json
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

from aiohttp import ClientError, ClientSession, ClientTimeout

from .const import APP_ID, CFB, CLIENT_ID, CLIENT_SECRET, SPA_API_URL, USER_AGENT, USER_API_URL
from .errors import (
    AccountLockedError,
    ApiError,
    AuthenticationError,
    BluelinkError,
    DeviceRegistrationError,
    GatewayRejectedError,
    PasswordChangeRequiredError,
    RequestFailedError,
    UnsupportedResponseError,
    UnsupportedVehicleError,
)
from .status import VehicleStatus, parse_ccs2_status

_LOGGER = logging.getLogger(__name__)

_REQUEST_TIMEOUT = ClientTimeout(total=30)
# 有効期限のこの時間前にログインし直す。
_TOKEN_REFRESH_MARGIN = timedelta(minutes=5)
_ERR_CODE_WRONG_CREDENTIALS = "4003"
_ERR_CODE_ACCOUNT_LOCKED = "4006"
_RES_CODE_INVALID_DEVICE = "4002"


@dataclass(frozen=True, slots=True)
class Vehicle:
    """アカウントに登録された車両。

    Attributes:
        vehicle_id: 状態取得に使う carId。
        name: 車両名。
        model: 車種名。
        is_ev: EV かどうか。
    """

    vehicle_id: str
    name: str
    model: str
    is_ev: bool


@dataclass(frozen=True, slots=True)
class _Response:
    status: int
    body: Any


def make_stamp(app_id: str, cfb: str, timestamp: int) -> str:
    """Stamp ヘッダーの値を作る。

    `{app_id}:{10桁の Unix 時刻}` の各バイトと CFB の XOR を base64 にする。

    Args:
        app_id: ccsp-application-id。
        cfb: 47 バイトの XOR マスク（base64）。
        timestamp: Unix 時刻（秒）。

    Returns:
        Stamp ヘッダーの値。

    Raises:
        ValueError: CFB が base64 でない場合や、入力と長さが合わない場合。
    """
    mask = base64.b64decode(cfb, validate=True)
    raw = f"{app_id}:{timestamp}".encode()
    if len(raw) != len(mask):
        raise ValueError("Stamp の入力と CFB の長さが一致しません")
    return base64.b64encode(bytes(b ^ m for b, m in zip(raw, mask, strict=True))).decode()


def _is_success(status: int) -> bool:
    return 200 <= status < 300


class BluelinkJpClient:
    """日本向け Bluelink のアカウント1件分のクライアント。

    Attributes:
        status_responses: 車両ごとの、最後に成功した状態取得の生応答（診断用）。
        fetch_results: 車両ごとの、最後の状態取得の結果（診断用）。
    """

    def __init__(self, session: ClientSession, email: str, password: str) -> None:
        """クライアントを作る。

        Args:
            session: cookie を他の統合と共有しない aiohttp セッション。ログインは cookie を使う。
            email: Bluelink アカウントのメールアドレス。
            password: Bluelink アカウントのパスワード。
        """
        self._session = session
        self._email = email
        self._password = password
        self._access_token: str | None = None
        self._token_expires_at: datetime | None = None
        self._device_id: str | None = None
        self.status_responses: dict[str, Any] = {}
        self.fetch_results: dict[str, dict[str, Any]] = {}

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
        form: dict[str, str] | None = None,
    ) -> _Response:
        try:
            async with self._session.request(
                method, url, headers=headers, json=json_body, data=form, timeout=_REQUEST_TIMEOUT
            ) as response:
                raw = await response.read()
                status = response.status
        except (ClientError, TimeoutError) as err:
            raise BluelinkError(f"Bluelink との通信に失敗しました（{type(err).__name__}）") from err
        try:
            body = json.loads(raw) if raw else None
        except ValueError:
            body = None
        return _Response(status, body)

    def _raise_for_status(self, response: _Response, action: str) -> None:
        if _is_success(response.status):
            return
        if response.status == 401:
            # 期限前に無効になったトークンは捨て、次の取得でログインし直す。
            self._access_token = None
        if response.status == 403:
            raise GatewayRejectedError(f"{action}が拒否されました", http_status=response.status)
        raise RequestFailedError(
            f"{action}に失敗しました（HTTP {response.status}）", http_status=response.status
        )

    async def async_login(self) -> None:
        """メールアドレスとパスワードでログインし、アクセストークンを得る。

        Raises:
            AuthenticationError: メールアドレスかパスワードが違う場合。
            AccountLockedError: アカウントが一時的にロックされている場合。
            BluelinkError: 通信やサーバーの応答に問題がある場合。
        """
        redirect_uri = USER_API_URL + "oauth2/redirect"
        # authorize で、以降の手順が使うログイン用セッションの cookie を受け取る。
        await self._request(
            "GET",
            f"{USER_API_URL}oauth2/authorize?response_type=code&state=test"
            f"&client_id={CLIENT_ID}&redirect_uri={redirect_uri}&lang=ja",
            headers={"User-Agent": USER_AGENT},
        )
        await self._async_set_session_language()
        code = await self._async_sign_in()
        await self._async_exchange_code(code, redirect_uri)
        _LOGGER.debug("Bluelink にログインしました")

    async def _async_set_session_language(self) -> None:
        # 公式の Web 版と同じく、サインインの前にセッションの言語を日本語にする。
        # authorize の lang=ja とは別の設定。失敗したら資格情報を送らずに止める。
        response = await self._request(
            "POST",
            USER_API_URL + "language",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            json_body={"lang": "ja"},
        )
        if not _is_success(response.status):
            raise RequestFailedError(
                f"セッション言語の設定に失敗しました（HTTP {response.status}）",
                http_status=response.status,
            )

    async def _async_sign_in(self) -> str:
        response = await self._request(
            "POST",
            USER_API_URL + "signin",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
            json_body={"email": self._email, "password": self._password, "mobileNum": None},
        )
        body = response.body if isinstance(response.body, dict) else {}
        if not 200 <= response.status < 304:
            err_code = str(body.get("errCode"))
            if err_code == _ERR_CODE_ACCOUNT_LOCKED:
                raise AccountLockedError(
                    "サインインの失敗が続いたため、アカウントが一時的にロックされています"
                )
            if err_code == _ERR_CODE_WRONG_CREDENTIALS:
                raise AuthenticationError("メールアドレスかパスワードが違います")
            raise RequestFailedError(
                f"サインインに失敗しました（HTTP {response.status}、errCode {err_code}）",
                http_status=response.status,
            )
        redirect_url = body.get("redirectUrl")
        if not isinstance(redirect_url, str):
            if body.get("step") == 5:
                raise PasswordChangeRequiredError(
                    "公式 Bluelink のログイン画面でパスワード変更の案内を確認してください"
                )
            raise UnsupportedResponseError(f"サインインの応答を処理できません（step={body.get('step')!r}）")
        codes = parse_qs(urlparse(redirect_url).query).get("code")
        if not codes:
            raise UnsupportedResponseError("サインインの応答に認可コードがありません")
        return codes[0]

    async def _async_exchange_code(self, code: str, redirect_uri: str) -> None:
        basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        response = await self._request(
            "POST",
            USER_API_URL + "oauth2/token",
            headers={"Authorization": f"Basic {basic}", "User-Agent": USER_AGENT},
            # 辞書で渡し、aiohttp に application/x-www-form-urlencoded として各値をエンコードさせる。
            form={"grant_type": "authorization_code", "redirect_uri": redirect_uri, "code": code},
        )
        body = response.body if isinstance(response.body, dict) else {}
        if not 200 <= response.status < 304 or "access_token" not in body:
            raise RequestFailedError(
                f"アクセストークンの取得に失敗しました（HTTP {response.status}）",
                http_status=response.status,
            )
        self._access_token = f"{body.get('token_type', 'Bearer')} {body['access_token']}"
        expires_in = body.get("expires_in")
        self._token_expires_at = (
            datetime.now(UTC) + timedelta(seconds=int(expires_in)) if expires_in else None
        )

    def _token_is_valid(self) -> bool:
        if self._access_token is None:
            return False
        if self._token_expires_at is None:
            return True
        return datetime.now(UTC) < self._token_expires_at - _TOKEN_REFRESH_MARGIN

    async def _async_ensure_logged_in(self) -> None:
        # ログインは対話なしで完結するので、期限が近づいたらパスワードでログインし直す。
        if not self._token_is_valid():
            self._access_token = None
            await self.async_login()

    def _account_headers(self) -> dict[str, str]:
        if self._access_token is None:
            raise BluelinkError("ログインしていません")
        return {"Authorization": self._access_token, "Accept": "application/json", "User-Agent": USER_AGENT}

    async def async_get_vehicles(self) -> list[Vehicle]:
        """アカウントに登録された車両の一覧を返す。

        Returns:
            車両の一覧。

        Raises:
            BluelinkError: ログイン、通信、応答のいずれかに問題がある場合。
        """
        await self._async_ensure_logged_in()
        response = await self._request("GET", USER_API_URL + "cars", headers=self._account_headers())
        self._raise_for_status(response, "車両一覧の取得")
        cars = response.body.get("cars") if isinstance(response.body, dict) else None
        if not isinstance(cars, list):
            raise UnsupportedResponseError("車両一覧の応答に cars がありません")
        return [
            Vehicle(
                vehicle_id=str(car["carId"]),
                name=car.get("carName") or car.get("vehicleName") or "Hyundai",
                model=car.get("vehicleName") or car.get("carName") or "",
                is_ev=car.get("carType") == "EV",
            )
            for car in cars
            if isinstance(car, dict) and car.get("carId")
        ]

    def _spa_headers(self) -> dict[str, str]:
        return {
            "ccsp-service-id": CLIENT_ID,
            "ccsp-application-id": APP_ID,
            "Stamp": make_stamp(APP_ID, CFB, int(time.time())),
            "Accept": "application/json",
            "Content-Type": "application/json;charset=UTF-8",
            "User-Agent": USER_AGENT,
        }

    async def _async_register_device(self) -> str:
        # 公式アプリと同じく、端末登録はアカウントの認証より前に行う。
        # 無効な Authorization を付けると正しい Stamp でも拒否されるので付けない。
        response = await self._request(
            "POST",
            SPA_API_URL + "notifications/register",
            headers=self._spa_headers(),
            json_body={
                "pushRegId": f"{uuid.uuid4().hex}{uuid.uuid4().hex}",
                "pushType": "GCM",
                "uuid": str(uuid.uuid4()),
            },
        )
        body = response.body if isinstance(response.body, dict) else {}
        if not _is_success(response.status) or body.get("retCode") not in (None, "S"):
            res_code = body.get("resCode")
            raise DeviceRegistrationError(
                f"端末登録に失敗しました（HTTP {response.status}）",
                http_status=response.status,
                res_code=None if res_code is None else str(res_code),
            )
        res_msg = body.get("resMsg")
        device_id = res_msg.get("deviceId") if isinstance(res_msg, dict) else body.get("deviceId")
        if not isinstance(device_id, str) or not device_id:
            raise DeviceRegistrationError("端末登録の応答に deviceId がありません")
        self._device_id = device_id
        _LOGGER.debug("状態取得用の端末を登録しました")
        return device_id

    async def async_get_vehicle_status(self, vehicle_id: str) -> VehicleStatus:
        """車がクラウドへ最後に同期した状態を取得する。車は起こさない。

        Args:
            vehicle_id: 車両の carId。

        Returns:
            車両状態。

        Raises:
            BluelinkError: ログイン、端末登録、通信、応答のいずれかに問題がある場合。
        """
        self.status_responses.pop(vehicle_id, None)
        try:
            status = await self._async_fetch_status(vehicle_id, retry_registration=True)
        except BluelinkError as err:
            self.fetch_results[vehicle_id] = {
                "state": err.reason,
                "http_status": err.http_status,
                "res_code": err.res_code,
            }
            raise
        self.fetch_results[vehicle_id] = {"state": "ok"}
        return status

    async def _async_fetch_status(self, vehicle_id: str, *, retry_registration: bool) -> VehicleStatus:
        await self._async_ensure_logged_in()
        device_id = self._device_id or await self._async_register_device()
        response = await self._request(
            "GET",
            f"{SPA_API_URL}vehicles/{vehicle_id}/ccs2/carstatus/latest",
            headers={
                **self._spa_headers(),
                **self._account_headers(),
                "ccsp-device-id": device_id,
                "Ccuccs2protocolsupport": "1",
            },
        )
        if response.status == 404:
            raise UnsupportedVehicleError(
                "この車両は CCS2 の状態取得に対応していません", http_status=response.status
            )
        self._raise_for_status(response, "車両状態の取得")
        body = response.body
        self.status_responses[vehicle_id] = body
        if isinstance(body, dict) and body.get("retCode") not in (None, "S"):
            res_code = None if body.get("resCode") is None else str(body.get("resCode"))
            if res_code == _RES_CODE_INVALID_DEVICE:
                # 再登録後の拒否でも登録を捨て、次の取得で新しく登録できるようにする。
                self._device_id = None
                if retry_registration:
                    _LOGGER.info("端末登録が拒否されたため、登録し直して1回だけ再試行します")
                    return await self._async_fetch_status(vehicle_id, retry_registration=False)
            raise ApiError(f"車両状態の取得が拒否されました（resCode {res_code}）", res_code=res_code)
        return parse_ccs2_status(body)

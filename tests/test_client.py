"""ログイン、端末登録、状態取得の HTTP の手順を、ローカルのモックサーバーで確かめる。"""

import base64
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from aiohttp import ClientSession, CookieJar, web
from aiohttp.resolver import ThreadedResolver
from aiohttp.test_utils import TestServer

from custom_components.hyundai_bluelink_jp.api import (
    AccountLockedError,
    ApiError,
    AuthenticationError,
    BluelinkJpClient,
    DeviceRegistrationError,
    GatewayRejectedError,
    RequestFailedError,
    UnsupportedVehicleError,
    Vehicle,
    make_stamp,
)
from custom_components.hyundai_bluelink_jp.api import client as client_module
from custom_components.hyundai_bluelink_jp.api.const import APP_ID, CFB, CLIENT_ID, CLIENT_SECRET

from .conftest import EMAIL, PASSWORD

NOW = 1700000000
LOGIN_CALLS = ["authorize", "language", "signin", "token"]


@dataclass
class FakeBluelink:
    """モックサーバーの状態と、受けた呼び出しの記録。"""

    body: Any
    calls: list[str] = field(default_factory=list)
    language_status: int = 204
    session_language: str = "en"
    signin_language: str | None = None
    signin_status: int = 200
    signin_err_code: str | None = None
    register_status: int = 200
    registered_devices: list[str] = field(default_factory=list)
    status_devices: list[str] = field(default_factory=list)
    status_code: int = 200
    status_bodies: list[Any] = field(default_factory=list)
    auth_code: str = "test-code"

    async def authorize(self, request: web.Request) -> web.StreamResponse:
        assert request.query["lang"] == "ja"
        assert request.query["client_id"] == CLIENT_ID
        self.calls.append("authorize")
        self.session_language = "en"
        response = web.HTTPFound("/login-page")
        response.set_cookie("login-session", "synthetic-session")
        raise response

    async def login_page(self, request: web.Request) -> web.Response:
        assert request.cookies["login-session"] == "synthetic-session"
        return web.Response(text="synthetic login page")

    async def language(self, request: web.Request) -> web.Response:
        assert request.cookies["login-session"] == "synthetic-session"
        assert "Authorization" not in request.headers
        assert await request.json() == {"lang": "ja"}
        self.calls.append("language")
        if self.language_status < 300:
            self.session_language = "ja"
        return web.Response(status=self.language_status)

    async def signin(self, request: web.Request) -> web.Response:
        assert request.cookies["login-session"] == "synthetic-session"
        assert await request.json() == {"email": EMAIL, "password": PASSWORD, "mobileNum": None}
        self.calls.append("signin")
        self.signin_language = self.session_language
        if self.signin_status != 200:
            return web.json_response({"errCode": self.signin_err_code}, status=self.signin_status)
        redirect = request.url.with_path("/redirect").with_query(code=self.auth_code)
        return web.json_response({"redirectUrl": str(redirect)})

    async def token(self, request: web.Request) -> web.Response:
        assert request.cookies["login-session"] == "synthetic-session"
        basic = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
        assert request.headers["Authorization"] == f"Basic {basic}"
        form = await request.post()
        assert form["grant_type"] == "authorization_code"
        assert form["redirect_uri"] == str(request.url.with_path("/user/oauth2/redirect").with_query(None))
        assert form["code"] == self.auth_code
        self.calls.append("token")
        return web.json_response({"token_type": "Bearer", "access_token": "test-token", "expires_in": 3600})

    async def cars(self, request: web.Request) -> web.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        self.calls.append("cars")
        return web.json_response(
            {
                "cars": [
                    {"carId": "test-car", "carName": "IONIQ 5", "vehicleName": "IONIQ 5", "carType": "EV"},
                    {"carName": "no id"},
                ]
            }
        )

    async def register(self, request: web.Request) -> web.Response:
        assert "Authorization" not in request.headers
        assert "ccsp-device-id" not in request.headers
        assert request.headers["ccsp-application-id"] == APP_ID
        assert request.headers["Stamp"] == make_stamp(APP_ID, CFB, NOW)
        self.calls.append("register")
        if self.register_status != 200:
            return web.json_response({"retCode": "F", "resCode": "9999"}, status=self.register_status)
        device_id = f"test-device-{len(self.registered_devices) + 1}"
        self.registered_devices.append(device_id)
        return web.json_response({"retCode": "S", "resMsg": {"deviceId": device_id}})

    async def status(self, request: web.Request) -> web.Response:
        assert request.headers["Authorization"] == "Bearer test-token"
        assert request.headers["Stamp"] == make_stamp(APP_ID, CFB, NOW)
        assert request.headers["Ccuccs2protocolsupport"] == "1"
        self.status_devices.append(request.headers["ccsp-device-id"])
        self.calls.append("status")
        body = self.status_bodies.pop(0) if self.status_bodies else self.body
        return web.json_response(body, status=self.status_code)

    def build_app(self) -> web.Application:
        """モックサーバーのアプリを作る。"""
        app = web.Application()
        app.router.add_get("/user/oauth2/authorize", self.authorize)
        app.router.add_get("/login-page", self.login_page)
        app.router.add_post("/user/language", self.language)
        app.router.add_post("/user/signin", self.signin)
        app.router.add_post("/user/oauth2/token", self.token)
        app.router.add_get("/user/cars", self.cars)
        app.router.add_post("/spa/notifications/register", self.register)
        app.router.add_get("/spa/vehicles/{vehicle_id}/ccs2/carstatus/latest", self.status)
        return app


@pytest.fixture
async def bluelink(
    monkeypatch: pytest.MonkeyPatch, socket_enabled: None, ccs2_body: dict[str, Any]
) -> AsyncIterator[tuple[BluelinkJpClient, FakeBluelink]]:
    """モックサーバーにつないだクライアント。"""
    monkeypatch.setattr("aiohttp.connector.DefaultResolver", ThreadedResolver)
    monkeypatch.setattr(client_module.time, "time", lambda: NOW)
    fake = FakeBluelink(body=ccs2_body)
    server = TestServer(fake.build_app())
    await server.start_server()
    monkeypatch.setattr(client_module, "USER_API_URL", str(server.make_url("/user/")))
    monkeypatch.setattr(client_module, "SPA_API_URL", str(server.make_url("/spa/")))
    try:
        # モックサーバーは IP アドレスなので、その cookie を受け付ける設定にする。
        async with ClientSession(cookie_jar=CookieJar(unsafe=True)) as session:
            yield BluelinkJpClient(session, EMAIL, PASSWORD), fake
    finally:
        await server.close()


def test_make_stamp() -> None:
    raw = f"{APP_ID}:{NOW}".encode()
    zero_mask = base64.b64encode(bytes(47)).decode()
    assert make_stamp(APP_ID, zero_mask, NOW) == base64.b64encode(raw).decode()
    stamp = base64.b64decode(make_stamp(APP_ID, CFB, NOW))
    mask = base64.b64decode(CFB)
    assert bytes(a ^ b for a, b in zip(stamp, mask, strict=True)) == raw
    with pytest.raises(ValueError, match="長さ"):
        make_stamp(APP_ID, base64.b64encode(bytes(46)).decode(), NOW)


@pytest.mark.parametrize("language_status", [200, 204])
async def test_login_sets_japanese_before_signin(
    bluelink: tuple[BluelinkJpClient, FakeBluelink], language_status: int
) -> None:
    client, fake = bluelink
    fake.language_status = language_status
    await client.async_login()
    assert fake.calls == LOGIN_CALLS
    assert fake.signin_language == "ja"


async def test_expired_token_logs_in_again(bluelink: tuple[BluelinkJpClient, FakeBluelink]) -> None:
    client, fake = bluelink
    assert await client.async_get_vehicles() == [
        Vehicle(vehicle_id="test-car", name="IONIQ 5", model="IONIQ 5", is_ev=True)
    ]
    assert fake.calls == [*LOGIN_CALLS, "cars"]
    fake.calls.clear()
    client._token_expires_at = None
    client._access_token = None
    await client.async_get_vehicles()
    assert fake.calls == [*LOGIN_CALLS, "cars"]
    assert fake.signin_language == "ja"


@pytest.mark.parametrize("language_status", [403, 503])
async def test_language_failure_stops_before_sending_credentials(
    bluelink: tuple[BluelinkJpClient, FakeBluelink], language_status: int
) -> None:
    client, fake = bluelink
    fake.language_status = language_status
    with pytest.raises(RequestFailedError, match="セッション言語") as err:
        await client.async_login()
    # サーバー側の失敗を、パスワードの誤り（再認証）として扱わない。
    assert not isinstance(err.value, AuthenticationError)
    assert fake.calls == ["authorize", "language"]


@pytest.mark.parametrize(
    ("status", "err_code", "error"),
    [
        (400, "4003", AuthenticationError),
        (400, "4006", AccountLockedError),
        (500, None, RequestFailedError),
    ],
)
async def test_signin_errors(
    bluelink: tuple[BluelinkJpClient, FakeBluelink],
    status: int,
    err_code: str | None,
    error: type[Exception],
) -> None:
    client, fake = bluelink
    fake.signin_status = status
    fake.signin_err_code = err_code
    with pytest.raises(error) as raised:
        await client.async_login()
    assert type(raised.value) is error
    assert PASSWORD not in str(raised.value)
    assert "token" not in fake.calls


async def test_status_registers_device_once(bluelink: tuple[BluelinkJpClient, FakeBluelink]) -> None:
    client, fake = bluelink
    status = await client.async_get_vehicle_status("test-car")
    assert status.ev_battery_level == 73
    assert client.fetch_results["test-car"] == {"state": "ok"}
    assert client.status_responses["test-car"] == fake.body
    await client.async_get_vehicle_status("test-car")
    assert fake.calls.count("register") == 1
    assert fake.calls.count("signin") == 1
    assert fake.status_devices == ["test-device-1", "test-device-1"]


@pytest.mark.parametrize(
    ("status_code", "error", "state"),
    [
        (404, UnsupportedVehicleError, "unsupported_vehicle"),
        (403, GatewayRejectedError, "gateway_rejected"),
        (500, RequestFailedError, "http_error"),
    ],
)
async def test_status_http_errors(
    bluelink: tuple[BluelinkJpClient, FakeBluelink],
    status_code: int,
    error: type[Exception],
    state: str,
) -> None:
    client, fake = bluelink
    fake.status_code = status_code
    with pytest.raises(error):
        await client.async_get_vehicle_status("test-car")
    assert client.fetch_results["test-car"] == {
        "state": state,
        "http_status": status_code,
        "res_code": None,
    }
    assert "test-car" not in client.status_responses


async def test_application_error_keeps_registration(
    bluelink: tuple[BluelinkJpClient, FakeBluelink],
) -> None:
    client, fake = bluelink
    fake.body = {"retCode": "F", "resCode": "4004"}
    with pytest.raises(ApiError):
        await client.async_get_vehicle_status("test-car")
    assert client.fetch_results["test-car"] == {
        "state": "api_error",
        "http_status": None,
        "res_code": "4004",
    }
    assert fake.calls.count("register") == 1
    assert client._device_id == "test-device-1"


async def test_invalid_device_recovers_once(bluelink: tuple[BluelinkJpClient, FakeBluelink]) -> None:
    client, fake = bluelink
    await client.async_get_vehicle_status("test-car")
    fake.status_bodies = [{"retCode": "F", "resCode": "4002"}]
    status = await client.async_get_vehicle_status("test-car")
    assert status.ev_battery_level == 73
    assert client.fetch_results["test-car"] == {"state": "ok"}
    assert fake.calls.count("register") == 2
    assert fake.status_devices == ["test-device-1", "test-device-1", "test-device-2"]


async def test_repeated_invalid_device_discards_registration(
    bluelink: tuple[BluelinkJpClient, FakeBluelink], ccs2_body: dict[str, Any]
) -> None:
    client, fake = bluelink
    fake.body = {"retCode": "F", "resCode": "4002"}
    with pytest.raises(ApiError):
        await client.async_get_vehicle_status("test-car")
    assert fake.calls.count("register") == 2
    assert fake.calls.count("status") == 2
    assert client._device_id is None
    # 次の定期取得で、再読み込みなしに新しく登録し直せる。
    fake.body = ccs2_body
    await client.async_get_vehicle_status("test-car")
    assert fake.calls.count("register") == 3
    assert client.fetch_results["test-car"] == {"state": "ok"}


async def test_registration_failure(bluelink: tuple[BluelinkJpClient, FakeBluelink]) -> None:
    client, fake = bluelink
    fake.register_status = 503
    with pytest.raises(DeviceRegistrationError):
        await client.async_get_vehicle_status("test-car")
    assert client.fetch_results["test-car"]["state"] == "device_registration_failed"
    assert "status" not in fake.calls


async def test_unauthorized_status_logs_in_on_next_fetch(
    bluelink: tuple[BluelinkJpClient, FakeBluelink],
) -> None:
    client, fake = bluelink
    fake.status_code = 401
    with pytest.raises(RequestFailedError) as err:
        await client.async_get_vehicle_status("test-car")
    assert not isinstance(err.value, AuthenticationError)
    fake.calls.clear()
    fake.status_code = 200
    await client.async_get_vehicle_status("test-car")
    assert fake.calls == [*LOGIN_CALLS, "status"]


async def test_authorization_code_is_form_encoded(bluelink: tuple[BluelinkJpClient, FakeBluelink]) -> None:
    client, fake = bluelink
    # フォームで意味を持つ文字を含む認可コードも、そのまま交換できる。
    fake.auth_code = "a+b/c&d=e%f g"
    await client.async_login()
    assert fake.calls == LOGIN_CALLS

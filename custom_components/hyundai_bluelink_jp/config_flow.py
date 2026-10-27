"""設定画面（メールアドレスとパスワード）と再認証。"""

from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    AccountLockedError,
    AuthenticationError,
    BluelinkError,
    BluelinkJpClient,
    PasswordChangeRequiredError,
    Vehicle,
)
from .const import DEFAULT_TITLE, DOMAIN

_PASSWORD_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_EMAIL): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        probatio.Required(CONF_PASSWORD): _PASSWORD_SELECTOR,
    }
)
REAUTH_SCHEMA = probatio.Schema({probatio.Required(CONF_PASSWORD): _PASSWORD_SELECTOR})


async def _async_fetch_vehicles(hass: HomeAssistant, email: str, password: str) -> list[Vehicle]:
    # 確認のためだけのセッション。HA 共有の接続プールを使うので、close() ではなく
    # detach() で切り離す（auto_cleanup=False のときの HA の作法）。
    session = async_create_clientsession(hass, auto_cleanup=False)
    try:
        client = BluelinkJpClient(session, email, password)
        await client.async_login()
        return await client.async_get_vehicles()
    finally:
        session.detach()


async def _async_validate(hass: HomeAssistant, email: str, password: str) -> str | None:
    """ログインと車両一覧の取得を試し、失敗したら画面に出すエラーのキーを返す。"""
    try:
        vehicles = await _async_fetch_vehicles(hass, email, password)
    except PasswordChangeRequiredError:
        return "password_change_required"
    except AuthenticationError:
        return "invalid_auth"
    except AccountLockedError:
        return "account_locked"
    except BluelinkError:
        return "cannot_connect"
    if not vehicles:
        return "no_vehicles"
    return None


class BluelinkJpConfigFlow(ConfigFlow, domain=DOMAIN):
    """日本向け Hyundai Bluelink の設定。"""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """メールアドレスとパスワードを受け取る。"""
        errors: dict[str, str] = {}
        if user_input is not None:
            email = user_input[CONF_EMAIL].strip()
            await self.async_set_unique_id(email.lower())
            self._abort_if_unique_id_configured()
            error = await _async_validate(self.hass, email, user_input[CONF_PASSWORD])
            if error is None:
                return self.async_create_entry(
                    title=DEFAULT_TITLE,
                    data={CONF_EMAIL: email, CONF_PASSWORD: user_input[CONF_PASSWORD]},
                )
            errors["base"] = error
        return self.async_show_form(
            step_id="user",
            # 入力し直しの画面でもパスワードは埋め戻さない。
            data_schema=self.add_suggested_values_to_schema(
                USER_SCHEMA, {CONF_EMAIL: user_input[CONF_EMAIL]} if user_input else None
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """パスワードが通らなくなったときに再認証を始める。"""
        return await self.async_step_reauth_confirm()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """設定済みアカウントのパスワードを変更する。"""
        errors: dict[str, str] = {}
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            error = await _async_validate(self.hass, entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error
        return self.async_show_form(step_id="reconfigure", data_schema=REAUTH_SCHEMA, errors=errors)

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """新しいパスワードを受け取る。"""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            error = await _async_validate(self.hass, entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            if error is None:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
            errors["base"] = error
        return self.async_show_form(step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors)

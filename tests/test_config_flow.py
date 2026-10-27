"""設定画面と再認証。"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_RECONFIGURE, SOURCE_USER
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hyundai_bluelink_jp.api import (
    AccountLockedError,
    AuthenticationError,
    BluelinkError,
    PasswordChangeRequiredError,
)
from custom_components.hyundai_bluelink_jp.const import DEFAULT_TITLE, DOMAIN

from .conftest import EMAIL, PASSWORD


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_client: SimpleNamespace) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: f" {EMAIL.upper()} ", CONF_PASSWORD: PASSWORD}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # タイトルにメールアドレスを出さない。
    assert result["title"] == DEFAULT_TITLE
    assert result["data"] == {CONF_EMAIL: EMAIL.upper(), CONF_PASSWORD: PASSWORD}
    assert result["result"].unique_id == EMAIL


@pytest.mark.parametrize(
    ("error", "vehicles", "reason"),
    [
        (AuthenticationError("wrong"), None, "invalid_auth"),
        (PasswordChangeRequiredError("change"), None, "password_change_required"),
        (AccountLockedError("locked"), None, "account_locked"),
        (BluelinkError("timeout"), None, "cannot_connect"),
        (None, [], "no_vehicles"),
    ],
)
async def test_user_flow_errors_then_recovers(
    hass: HomeAssistant,
    mock_client: SimpleNamespace,
    error: Exception | None,
    vehicles: list[object] | None,
    reason: str,
) -> None:
    default_vehicles = mock_client.vehicles.return_value
    mock_client.login.side_effect = error
    if vehicles is not None:
        mock_client.vehicles.return_value = vehicles
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": reason}

    mock_client.login.side_effect = None
    mock_client.vehicles.return_value = default_vehicles
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_same_account_is_rejected(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_EMAIL: EMAIL.upper(), CONF_PASSWORD: PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    mock_client.login.assert_not_called()


async def test_reauth_updates_password(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    mock_client.login.side_effect = AuthenticationError("wrong")
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "still-wrong"}
    )
    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data == {CONF_EMAIL: EMAIL, CONF_PASSWORD: "new-password"}


async def test_reconfigure_updates_existing_entry_after_failed_setup(
    hass: HomeAssistant, mock_client: SimpleNamespace, config_entry: MockConfigEntry
) -> None:
    config_entry.add_to_hass(hass)
    mock_client.login.side_effect = BluelinkError("unsupported response")
    await hass.config_entries.async_setup(config_entry.entry_id)
    assert config_entry.supports_reconfigure
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_RECONFIGURE, "entry_id": config_entry.entry_id}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    assert result["errors"] == {"base": "cannot_connect"}
    assert config_entry.data[CONF_PASSWORD] == PASSWORD

    mock_client.login.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.data == {CONF_EMAIL: EMAIL, CONF_PASSWORD: "new-password"}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_validation_session_is_detached(hass: HomeAssistant, mock_client: SimpleNamespace) -> None:
    # HA 共有の接続プールを閉じないよう、確認用のセッションは detach() で切り離す。
    with patch("custom_components.hyundai_bluelink_jp.config_flow.async_create_clientsession") as create:
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )
    create.return_value.detach.assert_called_once_with()
    create.return_value.close.assert_not_called()

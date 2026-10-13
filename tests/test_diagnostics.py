"""診断ファイルに、アカウント情報、トークン、識別子、位置が出ないこと。"""

import json
from types import SimpleNamespace
from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hyundai_bluelink_jp.diagnostics import async_get_config_entry_diagnostics

from .conftest import EMAIL, PASSWORD


async def test_diagnostics_redacts_private_values(
    hass: HomeAssistant,
    mock_client: SimpleNamespace,
    config_entry: MockConfigEntry,
    ccs2_body: dict[str, Any],
) -> None:
    config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    private = {
        key: f"private-value-{key}"
        for key in (
            "Authorization",
            "Stamp",
            "VIN",
            "accessToken",
            "access_token",
            "carId",
            "controlToken",
            "deviceId",
            "email",
            "refreshToken",
            "refresh_token",
            "token",
            "vehicleId",
            "vin",
        )
    }
    client = config_entry.runtime_data.client
    client.status_responses["test-car"] = {
        "retCode": "S",
        "resMsg": {"nested": [private], "state": ccs2_body["resMsg"]["state"]},
    }
    client.fetch_results["test-car"] = {"state": "ok"}

    diagnostics = await async_get_config_entry_diagnostics(hass, config_entry)
    serialized = json.dumps(diagnostics, default=str)
    for value in (EMAIL, PASSWORD, "test-car", *private.values()):
        assert value not in serialized
    assert "35.0" not in serialized
    assert "139.0" not in serialized

    vehicle = diagnostics["vehicles"][0]
    assert vehicle["fetch_result"] == {"state": "ok"}
    assert vehicle["status"]["ev_battery_level"] == 73
    assert vehicle["status"]["latitude"] == "**REDACTED**"
    raw_vehicle = vehicle["raw_response"]["resMsg"]["state"]["Vehicle"]
    assert raw_vehicle["Green"]["BatteryManagement"]["BatteryRemain"]["Ratio"] == 73
    assert raw_vehicle["Location"]["GeoCoord"] == "**REDACTED**"
    assert diagnostics["last_update_success"] is True

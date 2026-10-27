"""診断ファイル。アカウント情報、トークン、識別子、位置は伏せる。"""

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant

from .coordinator import BluelinkJpConfigEntry
from .history import IncidentHistory

TO_REDACT_ENTRY = {CONF_EMAIL, CONF_PASSWORD, "unique_id"}
TO_REDACT_STATUS = {"latitude", "longitude"}
# 生応答に含まれ得る、アカウント・車両・端末を特定できる値と位置。
TO_REDACT_RAW = {
    "Authorization",
    "GeoCoord",
    "Latitude",
    "Longitude",
    "Stamp",
    "VIN",
    "accessToken",
    "access_token",
    "carId",
    "controlToken",
    "deviceId",
    "email",
    "iccid",
    "invDealerCode",
    "lat",
    "latitude",
    "lon",
    "longitude",
    "mdn",
    "meid",
    "password",
    "preferredDealer",
    "refreshToken",
    "refresh_token",
    "token",
    "username",
    "vehicleId",
    "vin",
    "vinKey",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: BluelinkJpConfigEntry
) -> dict[str, Any]:
    """設定エントリーの診断情報を返す。車両 ID の代わりに通し番号を使う。"""
    if not hasattr(entry, "runtime_data"):
        history = IncidentHistory(hass, entry.entry_id)
        await history.async_load()
        return {
            "entry": async_redact_data(entry.as_dict(), TO_REDACT_ENTRY),
            "incidents": history.public_incidents(),
        }
    coordinator = entry.runtime_data
    client = coordinator.client
    vehicles: list[dict[str, Any]] = []
    for vehicle_id, vehicle in coordinator.vehicles.items():
        status = coordinator.data.statuses.get(vehicle_id) if coordinator.data else None
        raw_response = client.status_responses.get(vehicle_id)
        vehicles.append(
            {
                "name": vehicle.name,
                "model": vehicle.model,
                "is_ev": vehicle.is_ev,
                "fetch_result": client.fetch_results.get(vehicle_id, {"state": "not_requested"}),
                "fetched_at": coordinator.data.fetched_at.get(vehicle_id) if coordinator.data else None,
                "status": None if status is None else async_redact_data(asdict(status), TO_REDACT_STATUS),
                "raw_response": None
                if raw_response is None
                else async_redact_data(raw_response, TO_REDACT_RAW),
            }
        )
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT_ENTRY),
        "last_update_success": coordinator.last_update_success,
        "incidents": coordinator.history.public_incidents(),
        "vehicles": vehicles,
    }

"""車両状態を定期的に取得するコーディネーター。"""

import logging
from dataclasses import dataclass
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthenticationError, BluelinkError, BluelinkJpClient, Vehicle, VehicleStatus
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type BluelinkJpConfigEntry = ConfigEntry[BluelinkJpCoordinator]


@dataclass(frozen=True, slots=True)
class BluelinkJpData:
    """1回の取得の結果。

    Attributes:
        statuses: 車両ごとの状態。
        fetched_at: HA が取得に成功した時刻。車がクラウドへ同期した時刻とは別。
    """

    statuses: dict[str, VehicleStatus]
    fetched_at: datetime


class BluelinkJpCoordinator(DataUpdateCoordinator[BluelinkJpData]):
    """アカウントの全車両の状態をまとめて取得する。"""

    config_entry: BluelinkJpConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: BluelinkJpConfigEntry,
        client: BluelinkJpClient,
        vehicles: list[Vehicle],
    ) -> None:
        """コーディネーターを作る。

        Args:
            hass: Home Assistant。
            entry: この統合の設定エントリー。
            client: ログイン済みのクライアント。
            vehicles: アカウントの車両。
        """
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.vehicles = {vehicle.vehicle_id: vehicle for vehicle in vehicles}

    async def _async_update_data(self) -> BluelinkJpData:
        statuses: dict[str, VehicleStatus] = {}
        for vehicle_id in self.vehicles:
            try:
                statuses[vehicle_id] = await self.client.async_get_vehicle_status(vehicle_id)
            except AuthenticationError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except BluelinkError as err:
                # 取得の失敗は古い値で隠さず、エンティティを unavailable にする（Issue #1）。
                raise UpdateFailed(f"車両状態を取得できませんでした: {err}") from err
        return BluelinkJpData(statuses=statuses, fetched_at=dt_util.utcnow())

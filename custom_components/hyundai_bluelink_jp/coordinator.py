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
from .history import IncidentHistory, vehicle_scope

_LOGGER = logging.getLogger(__name__)

type BluelinkJpConfigEntry = ConfigEntry[BluelinkJpCoordinator]


@dataclass(frozen=True, slots=True)
class BluelinkJpData:
    """1回の取得の結果。

    Attributes:
        statuses: 取得に成功した車両ごとの状態。失敗した車両は含まない。
        fetched_at: 車両ごとに、HA が取得に成功した時刻。車がクラウドへ同期した時刻とは別。
    """

    statuses: dict[str, VehicleStatus]
    fetched_at: dict[str, datetime]


class BluelinkJpCoordinator(DataUpdateCoordinator[BluelinkJpData]):
    """アカウントの全車両の状態をまとめて取得する。"""

    config_entry: BluelinkJpConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: BluelinkJpConfigEntry,
        client: BluelinkJpClient,
        vehicles: list[Vehicle],
        history: IncidentHistory,
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
        self.history = history
        self.vehicles = {vehicle.vehicle_id: vehicle for vehicle in vehicles}
        self._failed_vehicle_ids: set[str] = set()

    async def _async_update_data(self) -> BluelinkJpData:
        statuses: dict[str, VehicleStatus] = {}
        failures: dict[str, BluelinkError] = {}
        for vehicle_id in self.vehicles:
            try:
                statuses[vehicle_id] = await self.client.async_get_vehicle_status(vehicle_id)
            except AuthenticationError as err:
                await self.history.async_failure("account", err)
                raise ConfigEntryAuthFailed(str(err)) from err
            except BluelinkError as err:
                failures[vehicle_id] = err
                await self.history.async_failure(vehicle_scope(vehicle_id), err)
            else:
                await self.history.async_recovery(vehicle_scope(vehicle_id))
        if statuses:
            await self.history.async_recovery("account")
        # 取得の失敗は古い値で隠さず、エンティティを unavailable にする（Issue #1）。
        # 1台だけの失敗は、その車両のエンティティだけを unavailable にする。
        if failures and not statuses:
            error = next(iter(failures.values()))
            raise UpdateFailed(f"車両状態を取得できませんでした: {error}") from error
        self._log_vehicle_failures(failures)
        now = dt_util.utcnow()
        return BluelinkJpData(statuses=statuses, fetched_at=dict.fromkeys(statuses, now))

    def _log_vehicle_failures(self, failures: dict[str, BluelinkError]) -> None:
        # 失敗し続ける車両で取得のたびに警告を出さないよう、状態が変わったときだけ記録する。
        for vehicle_id in failures.keys() - self._failed_vehicle_ids:
            _LOGGER.warning(
                "%s の状態を取得できませんでした: %s", self.vehicles[vehicle_id].name, failures[vehicle_id]
            )
        for vehicle_id in self._failed_vehicle_ids - failures.keys():
            _LOGGER.info("%s の状態を再び取得できました", self.vehicles[vehicle_id].name)
        self._failed_vehicle_ids = set(failures)

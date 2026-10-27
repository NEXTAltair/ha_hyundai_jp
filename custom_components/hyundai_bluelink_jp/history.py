"""障害の開始と復旧を、設定エントリーごとに保存する。"""

import asyncio
import hashlib
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import BluelinkError
from .const import DOMAIN

MAX_INCIDENTS = 200
_REASONS = {
    "communication_error",
    "invalid_auth",
    "password_change_required",
    "account_locked",
    "http_error",
    "gateway_rejected",
    "api_error",
    "device_registration_failed",
    "unsupported_vehicle",
    "unsupported_response",
}


def vehicle_scope(vehicle_id: str) -> str:
    """車両 ID 自体を履歴に保存しない。"""
    return "vehicle:" + hashlib.sha256(vehicle_id.encode()).hexdigest()


class IncidentHistory:
    """保存済み障害履歴と現在の障害を扱う。"""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.incidents.{entry_id}")
        self._lock = asyncio.Lock()
        self._incidents: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        """再起動前の履歴を読み込む。"""
        data = await self._store.async_load()
        self._incidents = data.get("incidents", []) if isinstance(data, dict) else []

    async def async_failure(self, scope: str, error: BluelinkError) -> None:
        """連続する同じ障害はまとめて保存する。"""
        async with self._lock:
            reason = error.reason if error.reason in _REASONS else "communication_error"
            active = next(
                (i for i in reversed(self._incidents) if i["scope"] == scope and i["ended"] is None), None
            )
            status = error.http_status if isinstance(error.http_status, int) else None
            now = dt_util.utcnow().isoformat()
            if active:
                active.update(last_seen=now, latest_reason=reason, latest_http_status=status)
                await self._store.async_save({"incidents": self._incidents})
                return
            self._incidents.append(
                {
                    "scope": scope,
                    "started": now,
                    "last_seen": now,
                    "ended": None,
                    "reason": reason,
                    "http_status": status,
                    "latest_reason": reason,
                    "latest_http_status": status,
                }
            )
            while len(self._incidents) > MAX_INCIDENTS:
                resolved = next(
                    (i for i, item in enumerate(self._incidents) if item["ended"] is not None), None
                )
                self._incidents.pop(0 if resolved is None else resolved)
            await self._store.async_save({"incidents": self._incidents})

    async def async_recovery(self, scope: str) -> None:
        """同じ対象の障害が実際に回復した時刻を残す。"""
        async with self._lock:
            active = next(
                (i for i in reversed(self._incidents) if i["scope"] == scope and i["ended"] is None), None
            )
            if active is not None:
                active["ended"] = dt_util.utcnow().isoformat()
                await self._store.async_save({"incidents": self._incidents})

    def public_incidents(self) -> list[dict[str, Any]]:
        """車両を識別できる値を含まない履歴を返す。"""
        return [
            {
                "target": "vehicle" if i["scope"].startswith("vehicle:") else "account",
                **{
                    k: i[k]
                    for k in (
                        "started",
                        "last_seen",
                        "ended",
                        "reason",
                        "http_status",
                        "latest_reason",
                        "latest_http_status",
                    )
                },
            }
            for i in self._incidents
        ]

    async def async_remove(self) -> None:
        """設定削除時に履歴を削除する。"""
        await self._store.async_remove()

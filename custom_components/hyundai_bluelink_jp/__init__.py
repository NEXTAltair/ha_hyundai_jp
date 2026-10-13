"""日本向け Hyundai Bluelink の Home Assistant 統合。"""

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import AuthenticationError, BluelinkError, BluelinkJpClient
from .coordinator import BluelinkJpConfigEntry, BluelinkJpCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: BluelinkJpConfigEntry) -> bool:
    """設定エントリーを読み込む。"""
    # ログインは cookie を使うので、他の統合と共有しないセッションを作る。
    # 設定エントリーの読み込み中に作ったセッションは、アンロード時に HA が閉じる。
    session = async_create_clientsession(hass)
    client = BluelinkJpClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    try:
        await client.async_login()
        vehicles = await client.async_get_vehicles()
    except AuthenticationError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except BluelinkError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = BluelinkJpCoordinator(hass, entry, client, vehicles)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BluelinkJpConfigEntry) -> bool:
    """設定エントリーをアンロードする。"""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

"""日本向け Hyundai Bluelink の Home Assistant 統合。"""

from homeassistant.components import persistent_notification
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import AuthenticationError, BluelinkError, BluelinkJpClient
from .coordinator import BluelinkJpConfigEntry, BluelinkJpCoordinator
from .history import IncidentHistory

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: BluelinkJpConfigEntry) -> bool:
    """設定エントリーを読み込む。"""
    history = IncidentHistory(hass, entry.entry_id)
    await history.async_load()
    # ログインは cookie を使うので、他の統合と共有しないセッションを作る。
    # 設定エントリーの読み込み中に作ったセッションは、アンロード時に HA が閉じる。
    session = async_create_clientsession(hass)
    client = BluelinkJpClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    try:
        await client.async_login()
        vehicles = await client.async_get_vehicles()
    except AuthenticationError as err:
        await history.async_failure("account", err)
        _notify_setup_failure(hass, entry, history)
        raise ConfigEntryAuthFailed(str(err)) from err
    except BluelinkError as err:
        await history.async_failure("account", err)
        _notify_setup_failure(hass, entry, history)
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = BluelinkJpCoordinator(hass, entry, client, vehicles, history)
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady, ConfigEntryAuthFailed:
        _notify_setup_failure(hass, entry, history)
        raise
    persistent_notification.async_dismiss(hass, f"hyundai_bluelink_jp_{entry.entry_id}")
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _notify_setup_failure(
    hass: HomeAssistant, entry: BluelinkJpConfigEntry, history: IncidentHistory
) -> None:
    """セットアップ失敗中は、センサーがなくても検出時刻を示す。"""
    active = [item for item in history.public_incidents() if item["ended"] is None]
    started = active[-1]["started"] if active else "不明"
    persistent_notification.async_create(
        hass,
        f"Bluelink の取得を開始できません。最初に検出した時刻: {started}。統合の画面で詳細を確認してください。",
        title="Hyundai Bluelink Japan の接続エラー",
        notification_id=f"hyundai_bluelink_jp_{entry.entry_id}",
    )


async def async_unload_entry(hass: HomeAssistant, entry: BluelinkJpConfigEntry) -> bool:
    """設定エントリーをアンロードする。"""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: BluelinkJpConfigEntry) -> None:
    """統合の削除時に、そのアカウントの履歴も削除する。"""
    await IncidentHistory(hass, entry.entry_id).async_remove()
    persistent_notification.async_dismiss(hass, f"hyundai_bluelink_jp_{entry.entry_id}")

import os
from typing import Tuple

from loguru import logger
from sdbus_async.dbus_daemon import FreedesktopDbus
from sdbus import (
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_property_async,
    dbus_signal_async,
    get_current_message,
)


SNIPixmap = Tuple[int, int, bytes]


class StatusNotifierItem(
    DbusInterfaceCommonAsync,
    interface_name="org.kde.StatusNotifierItem",
):
    def __init__(self) -> None:
        super().__init__()

    @dbus_property_async(property_signature="s")
    def category(self) -> str:
        return ""

    @dbus_property_async(property_signature="s")
    def id(self) -> str:
        return ""

    @dbus_property_async(property_signature="s")
    def title(self) -> str:
        return ""

    @dbus_property_async(property_signature="s")
    def status(self) -> str:
        return ""

    @dbus_property_async(property_signature="u")
    def window_id(self) -> int:
        return 0

    @dbus_property_async(property_signature="s")
    def icon_name(self) -> str:
        return ""

    @dbus_property_async(property_signature="a(iiay)")
    def icon_pixmap(self) -> list[SNIPixmap]:
        return []

    @dbus_property_async(property_signature="s")
    def overlay_icon_name(self) -> str:
        return ""

    @dbus_property_async(property_signature="a(iiay)")
    def overlay_icon_pixmap(self) -> list[SNIPixmap]:
        return []

    @dbus_property_async(property_signature="s")
    def attention_icon_name(self) -> str:
        return ""

    @dbus_property_async(property_signature="a(iiay)")
    def attention_icon_pixmap(self) -> list[Tuple[SNIPixmap]]:
        return []

    @dbus_property_async(property_signature="s")
    def attention_movie_name(self) -> str:
        return ""

    @dbus_property_async(property_signature="(sa(iiay)ss)")
    def tool_tip(self) -> Tuple[str, list[SNIPixmap], str, str]:
        return ("", [], "", "")

    @dbus_property_async(property_signature="b")
    def item_is_menu(self) -> bool:
        return False

    @dbus_property_async(property_signature="o")
    def menu(self) -> str:
        return ""

    @dbus_method_async(input_signature="ii", result_signature="")
    async def context_menu(self) -> None:
        return None

    @dbus_method_async(input_signature="ii", result_signature="")
    async def activate(self) -> None:
        return None

    @dbus_method_async(input_signature="ii", result_signature="")
    async def secondary_activate(self) -> None:
        return None

    @dbus_method_async(input_signature="is", result_signature="")
    async def scroll(self) -> None:
        return None

    @dbus_signal_async(signal_signature="")
    async def new_title(self) -> None:
        return None

    @dbus_signal_async(signal_signature="")
    async def new_icon(self) -> None:
        return None

    @dbus_signal_async(signal_signature="")
    async def new_attention_icon(self) -> None:
        return None

    @dbus_signal_async(signal_signature="")
    async def new_overlay_icon(self) -> None:
        return None

    @dbus_signal_async(signal_signature="")
    async def new_tool_tip(self) -> None:
        return None

    @dbus_signal_async(signal_signature="")
    async def new_status(self) -> None:
        return None


class StatusNotifierWatcher(
    DbusInterfaceCommonAsync,
    # NOTE: It looks like most/all apps use the org.kde.* interfaces instead
    # of the org.freedesktop.* variants.
    interface_name="org.kde.StatusNotifierWatcher",
):
    _hosts: list[str] = []
    _items: list[str] = []

    def __init__(self) -> None:
        super().__init__()
        self._dbus = FreedesktopDbus.new_proxy(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
        )

    @dbus_method_async(input_signature="s", result_signature="")
    async def register_status_notifier_host(self, host: str) -> None:
        if host in self._hosts:
            logger.debug(f"Host {host} already registered to watcher.")
            return

        self._hosts.append(host)
        self.status_notifier_host_registered.emit(host)
        logger.debug(f"Registered new host {host} to watcher.")

    @dbus_method_async(input_signature="s", result_signature="")
    async def register_status_notifier_item(
        self,
        service_or_path: str,
    ) -> None:
        self._items.append(service_or_path)
        print(service_or_path)
        if service_or_path[0] == "/":
            service = get_current_message().sender or ""
            path = service_or_path
        else:
            service = service_or_path
            path = "/StatusNotifierItem"

        item = service + path

        if item in self._items:
            logger.debug(f"Item {item} already registered to watcher.")
            return

        self._items.append(item)
        self.status_notifier_item_registered.emit(item)
        logger.debug(f"Registered new item {item} to watcher.")

    @dbus_property_async(property_signature="as")
    def registered_status_notifier_items(self) -> list[str]:
        return self._items

    @dbus_property_async(property_signature="b")
    def is_status_notifier_host_registered(self) -> bool:
        return len(self._hosts) > 0

    @dbus_property_async(property_signature="i")
    def protocol_version(self) -> int:
        return 0

    @dbus_signal_async(signal_signature="s")
    def status_notifier_host_registered(self) -> str:
        raise NotImplementedError

    @dbus_signal_async(signal_signature="s")
    def status_notifier_item_registered(self) -> str:
        raise NotImplementedError

    @dbus_signal_async(signal_signature="s")
    def status_notifier_item_unregistered(self) -> str:
        raise NotImplementedError

    async def watch(self) -> None:
        async for payload in self._dbus.name_owner_changed:
            service, _, new_owner = payload

            if not new_owner:
                removed_items = list(filter(
                    lambda i: i.startswith(service),
                    self._items,
                ))
                self._items = list(filter(
                    lambda i: not i.startswith(service),
                    self._items,
                ))
                if service in self._hosts:
                    self._hosts.remove(service)
                    logger.debug(f"Removed host {service} from watcher.")

                for item in removed_items:
                    self.status_notifier_item_unregistered.emit(item)
                    logger.debug(f"Removed item {item} from watcher.")


class StatusNotifierHost(
    DbusInterfaceCommonAsync,
    interface_name="org.kde.StatusNotifierHost",
):
    def __init__(self) -> None:
        super().__init__()
        self._dbus = FreedesktopDbus.new_proxy(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
        )
        self._watcher = StatusNotifierWatcher.new_proxy(
            "org.kde.StatusNotifierWatcher",
            "/StatusNotifierWatcher",
        )
        self._service_name = f"org.kde.StatusNotifierHost-{os.getpid()}"

    async def handle_watcher_registration(self) -> None:
        async for payload in self._dbus.name_owner_changed:
            service, old_owner, _ = payload

            if not old_owner and service == "org.kde.StatusNotifierWatcher":
                await self._watcher.register_status_notifier_host(
                    self._service_name
                )

    async def handle_item_registered(self) -> None:
        async for item in self._watcher.status_notifier_item_registered:
            logger.debug(f"Registered item {item} to host.")

    async def handle_item_unregistered(self) -> None:
        async for item in self._watcher.status_notifier_item_unregistered:
            logger.debug(f"Removed item {item} from host.")
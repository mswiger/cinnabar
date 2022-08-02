import asyncio
import os
import threading

from gi.repository import Gtk
from loguru import logger
from sdbus_async.dbus_daemon import FreedesktopDbus
from sdbus import (
    DbusInterfaceCommonAsync,
    dbus_method_async,
    dbus_property_async,
    dbus_signal_async,
    get_current_message,
    request_default_bus_name_async,
)

from cinnabar.bar import Bar, WidgetPlugin


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
        self._dbus_proxy = FreedesktopDbus.new_proxy(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
        )

    @dbus_method_async(input_signature="s", result_signature="")
    async def register_status_notifier_host(self, host: str) -> None:
        if host in self._hosts:
            logger.debug(f"Host {host} already registered, ignoring.")
            return

        self._hosts.append(host)
        self.status_notifier_host_registered.emit(host)
        logger.debug(f"Registered new host {host}.")

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
            logger.debug(f"Item {item} already registred, ignoring.")
            return

        self._items.append(item)
        self.status_notifier_item_registered.emit(item)
        logger.debug(f"Registered new item {item}.")

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
        async for payload in self._dbus_proxy.name_owner_changed:
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
                    logger.debug(f"Removed host {service}.")

                for item in removed_items:
                    self.status_notifier_item_unregistered.emit(item)

                if len(removed_items) > 0:
                    logger.debug(f"Removed items: {', '.join(removed_items)}")


class StatusNotifierHost(
    DbusInterfaceCommonAsync,
    interface_name="org.kde.StatusNotifierHost",
):
    def __init__(self) -> None:
        super().__init__()
        self._dbus_proxy = FreedesktopDbus.new_proxy(
            "org.freedesktop.DBus",
            "/org/freedesktop/DBus",
        )
        self._watcher_proxy = StatusNotifierWatcher.new_proxy(
            "org.kde.StatusNotifierWatcher",
            "/StatusNotifierWatcher",
        )
        self._service_name = f"org.kde.StatusNotifierHost-{os.getpid()}"

    async def register_to_watcher(self) -> None:
        async for payload in self._dbus_proxy.name_owner_changed:
            service, old_owner, _ = payload

            if not old_owner and service == "org.kde.StatusNotifierWatcher":
                await self._watcher_proxy.register_status_notifier_host(
                    self._service_name
                )

    async def handle_item_registered(self) -> None:
        pass

    async def handle_item_unregistered(self) -> None:
        pass


class Tray(WidgetPlugin):
    def __init__(self, bar: Bar, config: dict) -> None:
        self._event_loop = asyncio.new_event_loop()
        thread = threading.Thread(
            target=self._run_event_loop,
            args=(self._event_loop,),
            daemon=True,
        )
        thread.start()

        self._watcher_future = asyncio.run_coroutine_threadsafe(
            self._start_watcher(),
            self._event_loop,
        )

    def __del__(self) -> None:
        self._watcher_future.cancel()

    def widget(self) -> Gtk.Widget:
        return Gtk.Box()

    def _run_event_loop(self, event_loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(event_loop)
        event_loop.run_forever()

    async def _start_watcher(self) -> None:
        self._watcher = StatusNotifierWatcher()
        await request_default_bus_name_async("org.kde.StatusNotifierWatcher")
        self._watcher.export_to_dbus("/StatusNotifierWatcher")
        await self._watcher.watch()

import asyncio
import os
import threading
from concurrent.futures import Future
from typing import Coroutine, Set

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


class Tray(WidgetPlugin):
    _watcher: StatusNotifierWatcher = StatusNotifierWatcher()
    _host: StatusNotifierHost = StatusNotifierHost()
    _event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    _running_tasks: Set[Future] = set()

    def __init__(self, bar: Bar, config: dict) -> None:
        event_loop_thread = threading.Thread(
            target=event_loop_worker,
            args=(self._event_loop,),
            daemon=True,
        )
        event_loop_thread.start()

        self._create_task(self._start_watcher())
        self._create_task(self._host.handle_watcher_registration())
        self._create_task(self._host.handle_item_registered())
        self._create_task(self._host.handle_item_unregistered())

    def __del__(self) -> None:
        for task in self._running_tasks:
            task.cancel()

    def widget(self) -> Gtk.Widget:
        return Gtk.Box()

    def _create_task(self, coroutine: Coroutine) -> Future:
        future = asyncio.run_coroutine_threadsafe(coroutine, self._event_loop)
        self._running_tasks.add(future)
        return future

    async def _start_watcher(self) -> None:
        await request_default_bus_name_async("org.kde.StatusNotifierWatcher")
        self._watcher.export_to_dbus("/StatusNotifierWatcher")
        await self._watcher.watch()


def event_loop_worker(event_loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(event_loop)
    event_loop.run_forever()

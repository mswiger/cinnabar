import asyncio
import threading
from concurrent.futures import Future
from typing import Coroutine, Set

from gi.repository import Gtk
from sdbus import request_default_bus_name_async

from cinnabar.bar import Bar, WidgetPlugin
from cinnabar.plugins.tray.sni import (
    StatusNotifierHost,
    StatusNotifierWatcher,
)


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
        return Gtk.Label(label="TRAY")

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

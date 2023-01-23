import asyncio
import threading
from concurrent.futures import Future
from typing import Coroutine

from gi.repository import Gdk, Gtk
from loguru import logger
from sdbus import request_default_bus_name_async

from cinnabar.bar import Bar, WidgetPlugin
from cinnabar.plugins.tray.sni import (
    StatusNotifierHost,
    StatusNotifierItem,
    StatusNotifierWatcher,
    parse_item_str,
)
from cinnabar.util import glib_call_in_main


class AsyncTaskManager:
    _event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
    _running_tasks: set[Future] = set()

    def __init__(self) -> None:
        event_loop_thread = threading.Thread(
            target=self._event_loop_worker,
            args=(self._event_loop,),
            daemon=True,
        )
        event_loop_thread.start()

    def __del__(self) -> None:
        for task in self._running_tasks:
            task.cancel()

    def run(self, coroutine: Coroutine) -> Future:
        def done(future: Future) -> None:
            exception = future.exception()
            if exception:
                raise exception
            self._running_tasks.remove(future)

        future = asyncio.run_coroutine_threadsafe(coroutine, self._event_loop)
        future.add_done_callback(done)
        self._running_tasks.add(future)
        return future

    def _event_loop_worker(self, loop: asyncio.AbstractEventLoop) -> None:
        asyncio.set_event_loop(loop)
        loop.run_forever()


class Item:
    _task_manager: AsyncTaskManager

    _item_proxy: StatusNotifierItem

    _tray_box: Gtk.Box
    _button: Gtk.Button
    _icon_theme: Gtk.IconTheme = Gtk.IconTheme()
    _menu: Gtk.Menu

    _service: str
    _path: str

    # TODO: are these glib_call_in_main decorations necessary?
    @glib_call_in_main
    def __init__(
        self,
        task_manager: AsyncTaskManager,
        service: str,
        path: str,
        icon_size: int,
        tray_box: Gtk.Box,
    ):
        self._task_manager = task_manager
        self._item_proxy = StatusNotifierItem.new_proxy(service, path)
        self._icon_size = icon_size
        self._tray_box = tray_box

        self._service = service
        self._path = path

        self._button = Gtk.Button(
            label="",
            relief=Gtk.ReliefStyle.NONE,
            always_show_image=True,
            visible=True,
        )

        self._task_manager.run(self._load_properties())

    async def _load_properties(self):
        properties = await self._item_proxy.properties_get_all_dict(
            on_unknown_member="ignore"
        )

        icon_theme_path = properties.get("icon_theme_path")
        icon_name = properties.get("icon_name", "image-missing")
        self._load_icon(icon_theme_path, icon_name)

    @glib_call_in_main
    def _load_icon(self, icon_theme_path: str | None, icon_name: str):
        paths = []
        if icon_theme_path:
            paths += [icon_theme_path]
        paths += Gtk.IconTheme.get_default().get_search_path()

        self._icon_theme.set_search_path(paths)
        self._icon_theme.rescan_if_needed()

        def on_size_allocate(button: Gtk.Button, _) -> None:
            window = self._tray_box.get_window()
            scale = window.get_scale_factor() if window is not None else 1

            # Use the height of the button for the icon if the configured icon
            # size "scalable," else use the configured icon size.
            btn_height = button.get_children()[0].get_allocated_height()
            icon_size = btn_height if self._icon_size < 1 else self._icon_size

            sizes = self._icon_theme.get_icon_sizes(icon_name)
            if len(sizes) > 0 and sizes.count(icon_size) == 0:
                sizes.sort(reverse=True)
                icon_size = sizes[0]

            if icon_name:
                icon_pixbuf = self._icon_theme.load_icon_for_scale(
                    icon_name,
                    icon_size,
                    scale,
                    Gtk.IconLookupFlags.FORCE_SIZE,
                )

                if icon_pixbuf is not None:
                    surface = Gdk.cairo_surface_create_from_pixbuf(
                        icon_pixbuf,
                        0,
                        self._tray_box.get_window(),
                    )
                    button.set_image(Gtk.Image.new_from_surface(surface))
                    button.disconnect(handler_id)
            # TODO: Add case for handling pixmap directly (no icon name set)

        handler_id = self._button.connect("size_allocate", on_size_allocate)
        self._tray_box.add(self._button)


class Tray(WidgetPlugin):
    _watcher: StatusNotifierWatcher = StatusNotifierWatcher()
    _watcher_proxy: StatusNotifierWatcher
    _host: StatusNotifierHost = StatusNotifierHost()
    _task_manager: AsyncTaskManager = AsyncTaskManager()
    _items: dict = dict()

    def __init__(self, bar: Bar, config: dict) -> None:
        self._bar = bar
        self._config = config
        self._task_manager.run(self._start_watcher())
        self._task_manager.run(self._host.watch())

        self._box = Gtk.Box()

    def widget(self) -> Gtk.Widget:
        return self._box

    async def _start_watcher(self) -> None:
        await request_default_bus_name_async("org.kde.StatusNotifierWatcher")
        self._watcher.export_to_dbus("/StatusNotifierWatcher")

        self._watcher_proxy = StatusNotifierWatcher.new_proxy(
            "org.kde.StatusNotifierWatcher",
            "/StatusNotifierWatcher",
        )

        self._task_manager.run(self._handle_item_registered())
        self._task_manager.run(self._handle_item_unregistered())

    async def _handle_item_registered(self) -> None:
        async for i in self._watcher_proxy.status_notifier_item_registered:
            logger.debug(f"Registered item {i} to host.")
            service, path = parse_item_str(i)
            self._items[i] = Item(
                self._task_manager,
                service,
                path,
                self.icon_size,
                self._box
            )

    async def _handle_item_unregistered(self) -> None:
        async for itm in self._watcher_proxy.status_notifier_item_unregistered:
            logger.debug(f"Removed item {itm} from host.")

    @property
    def icon_size(self):
        configured_size = int(self._config.get("icon_size", 24))

        if configured_size < 1:
            configured_size = 0

        return configured_size

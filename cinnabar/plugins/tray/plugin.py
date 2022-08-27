import asyncio
import threading
from concurrent.futures import Future
from typing import Coroutine, Set

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


class Tray(WidgetPlugin):
    _watcher: StatusNotifierWatcher = StatusNotifierWatcher()
    _watcher_proxy: StatusNotifierWatcher
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

        self._bar = bar
        self._create_task(self._start_watcher())
        self._create_task(self._host.watch())

        self._box = Gtk.Box()

    def __del__(self) -> None:
        for task in self._running_tasks:
            task.cancel()

    def widget(self) -> Gtk.Widget:
        return self._box

    def _create_task(self, coroutine: Coroutine) -> Future:
        def done(future: Future) -> None:
            exception = future.exception()
            if exception:
                raise exception

        future = asyncio.run_coroutine_threadsafe(coroutine, self._event_loop)
        future.add_done_callback(done)
        self._running_tasks.add(future)
        return future

    async def _start_watcher(self) -> None:
        await request_default_bus_name_async("org.kde.StatusNotifierWatcher")
        self._watcher.export_to_dbus("/StatusNotifierWatcher")

        self._watcher_proxy = StatusNotifierWatcher.new_proxy(
            "org.kde.StatusNotifierWatcher",
            "/StatusNotifierWatcher",
        )

        self._create_task(self._handle_item_registered())
        self._create_task(self._handle_item_unregistered())

    async def _handle_item_registered(self) -> None:
        async for i in self._watcher_proxy.status_notifier_item_registered:
            logger.debug(f"Registered item {i} to host.")
            service, path = parse_item_str(i)
            # NOTE: Will either have icon name or icon pixmap
            item_proxy = StatusNotifierItem.new_proxy(service, path)
            properties = await item_proxy.properties_get_all_dict(
                on_unknown_member="ignore"
            )

            self._add_item(properties)

    def _add_item(self, properties: dict) -> None:
        button = Gtk.Button(
            label="",
            relief=Gtk.ReliefStyle.NONE,
            always_show_image=True,
            visible=True,
        )

        # Create the image after space for the button has been allocated so
        # the image size matches the size of the inside of the button.
        def on_size_allocate(button: Gtk.Button, _) -> None:
            window = self._box.get_window()
            scale = window.get_scale_factor() if window is not None else 1
            icon_size = button.get_children()[0].get_allocated_height()
            icon_name = properties.get("icon_name")

            if icon_name:
                icon_theme = Gtk.IconTheme.get_default()
                icon_pixbuf = icon_theme.load_icon_for_scale(
                    icon_name,
                    icon_size,
                    scale,
                    Gtk.IconLookupFlags.FORCE_SIZE,
                )

                if icon_pixbuf is not None:
                    surface = Gdk.cairo_surface_create_from_pixbuf(
                        icon_pixbuf,
                        0,
                        self._box.get_window(),
                    )
                    button.set_image(Gtk.Image.new_from_surface(surface))
                    button.disconnect(handler_id)
            # TODO: Add case for handling pixmap directly (no icon name set)

        handler_id = button.connect("size_allocate", on_size_allocate)
        self._box.add(button)

    async def _handle_item_unregistered(self) -> None:
        async for itm in self._watcher_proxy.status_notifier_item_unregistered:
            logger.debug(f"Removed item {itm} from host.")


def event_loop_worker(event_loop: asyncio.AbstractEventLoop) -> None:
    asyncio.set_event_loop(event_loop)
    event_loop.run_forever()

from __future__ import annotations

import importlib
import inspect
from abc import ABC, abstractmethod
from enum import Enum

from gi.repository import Gdk, Gtk, GtkLayerShell


class BarPosition(Enum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"

    @classmethod
    def from_str(cls, string: str) -> BarPosition:
        key = string.upper()
        for val in BarPosition:
            if key == val.name:
                return val

        raise ValueError(
            "'{}' is not a valid BarPosition, "
            "must be top, bottom, left, or right".format(str)
        )

    def to_layer_shell_edge(self) -> GtkLayerShell.Edge:
        match self:
            case BarPosition.TOP:
                return GtkLayerShell.Edge.TOP
            case BarPosition.BOTTOM:
                return GtkLayerShell.Edge.BOTTOM
            case BarPosition.LEFT:
                return GtkLayerShell.Edge.LEFT
            case BarPosition.RIGHT:
                return GtkLayerShell.Edge.RIGHT


class Bar:
    monitor: Gdk.Monitor
    """Monitor object the bar is attached to."""

    output: str
    """Name of the output the bar is attached to."""

    _position: BarPosition
    """Which edge of the screen the bar should be anchored to."""

    _begin_widgets: list[WidgetPlugin] = []
    _mid_widgets: list[WidgetPlugin] = []
    _end_widgets: list[WidgetPlugin] = []

    @property
    def orientation(self) -> Gtk.Orientation:
        if self._position in [BarPosition.LEFT, BarPosition.RIGHT]:
            return Gtk.Orientation.VERTICAL
        return Gtk.Orientation.HORIZONTAL

    def __init__(
        self,
        app: Gtk.Application,
        monitor: Gdk.Monitor,
        output: str,
        config: dict,
    ) -> None:
        self._app = app
        self.monitor = monitor
        self.output = output
        self._config = config

        self._width = int(config.get("width", 0))
        self._height = int(config.get("height", 0))
        self._position = BarPosition.from_str(config.get("position", "top"))

        widget_config = config.get("widgets", {})
        self._begin_widgets = self._load_widgets(
            widget_config.get("beginning", [])
        )
        self._mid_widgets = self._load_widgets(
            widget_config.get("middle", [])
        )
        self._end_widgets = self._load_widgets(
            widget_config.get("end", [])
        )

        self._init_window()

    def __del__(self):
        self._window.hide()
        self._app.remove_window(self._window)

    def _load_widgets(self, configs: list[dict]) -> list[WidgetPlugin]:
        widgets: list[WidgetPlugin] = []
        for config in configs:
            plugin_module_path = "cinnabar.plugins." + config["widget"]
            module = importlib.import_module(plugin_module_path)
            classes = inspect.getmembers(module, inspect.isclass)
            for (_, c) in classes:
                if issubclass(c, WidgetPlugin) and (c is not WidgetPlugin):
                    widgets.append(c(self, config))
        return widgets

    def _init_window(self):
        self._beginning_box = Gtk.Box(orientation=self.orientation, spacing=0)
        self._middle_box = Gtk.Box(orientation=self.orientation, spacing=0)
        self._end_box = Gtk.Box(orientation=self.orientation, spacing=0)

        self._main_box = Gtk.Box(orientation=self.orientation, spacing=0)
        self._main_box.pack_start(self._beginning_box, False, False, 0)
        self._main_box.set_center_widget(self._middle_box)
        self._main_box.pack_end(self._end_box, False, False, 0)

        for widget in self._begin_widgets:
            self._beginning_box.add(widget.widget())

        for widget in self._mid_widgets:
            self._middle_box.add(widget.widget())

        for widget in self._end_widgets:
            self._end_box.add(widget.widget())

        self._window = Gtk.Window(application=self._app, decorated=False)
        self._window.connect("destroy", Gtk.main_quit)
        self._window.add(self._main_box)

        GtkLayerShell.init_for_window(self._window)
        GtkLayerShell.auto_exclusive_zone_enable(self._window)
        GtkLayerShell.set_monitor(self._window, self.monitor)
        GtkLayerShell.set_namespace(self._window, "cinnabar")

        edges = [self._position.to_layer_shell_edge()]
        if self.orientation == Gtk.Orientation.HORIZONTAL and not self._width:
            edges.extend([GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT])
        elif self.orientation == Gtk.Orientation.VERTICAL and not self._height:
            edges.extend([GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM])

        for edge in edges:
            GtkLayerShell.set_anchor(self._window, edge, True)

        self._window.set_size_request(self._width, self._height)
        self._window.show_all()


class WidgetPlugin(ABC):
    """Plugin that represents a widget that can be added to a bar."""

    @abstractmethod
    def __init__(self, bar: Bar, config: dict):
        """Initialize the widget plugin

        Args:
            bar (Bar): The bar that the WidgetPlugin belongs to.
            config (dict): The configuration specific to the WidgetPlugin.
        """

        pass

    @abstractmethod
    def widget(self) -> Gtk.Widget:
        """Get the widget to display in the bar.

        Returns:
            Gtk.Widget: The widget to be displayed in the bar.
        """
        pass

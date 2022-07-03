from __future__ import annotations

import importlib
import inspect
import signal
from enum import Enum

import tomli
from gi.repository import Gio, GLib, Gtk, GtkLayerShell

from cinnabar.module import Module


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


class Configuration:
    def __init__(self):
        self.position = BarPosition.TOP

    @property
    def orientation(self) -> Gtk.Orientation:
        if self.position in [BarPosition.TOP, BarPosition.BOTTOM]:
            return Gtk.Orientation.HORIZONTAL
        return Gtk.Orientation.VERTICAL


class Application(Gtk.Application):
    def __init__(self, *args, **kwargs) -> None:
        flags = (
            Gio.ApplicationFlags.NON_UNIQUE
            | Gio.ApplicationFlags.HANDLES_COMMAND_LINE
        )

        super().__init__(
            *args,
            application_id="dev.swiger.Cinnabar",
            flags=flags,
            **kwargs,
        )

        self.config = Configuration()

        self.add_main_option(
            "position",
            ord("p"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.STRING,
            "Position of the bar on the display (top, bottom, left, right)",
        )

        self.add_main_option(
            "config",
            ord("c"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.STRING,
            "Config file to use",
        )

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.quit)
        self._modules_beginning = []

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict()
        options = options.end().unpack()

        if "position" in options:
            self.config.position = BarPosition.from_str(options["position"])
        if "config" in options:
            with open(options["config"], "rb") as f:
                cfg = tomli.load(f)
                module_cfg = cfg.get("modules", {})
                self._modules_beginning = self.load_module_list(
                    module_cfg.get("beginning", [])
                )
                self._modules_middle = self.load_module_list(
                    module_cfg.get("middle", [])
                )
                self._modules_end = self.load_module_list(
                    module_cfg.get("end", [])
                )
        self.activate()
        return 0

    def load_module_list(self, module_configs: list[dict]) -> list[Module]:
        # TODO: Should namespace package be used for Cinnabar modules?
        modules: list[Module] = []
        for module_config in module_configs:
            py_module = importlib.import_module(module_config["type"])
            classes = inspect.getmembers(py_module, inspect.isclass)
            for (_, c) in classes:
                if issubclass(c, Module) and (c is not Module):
                    modules.append(c(module_config))
        return modules

    def do_activate(self) -> None:
        beginning_box = Gtk.Box(orientation=self.config.orientation, spacing=0)
        beginning_box.set_halign(Gtk.Align.START)
        beginning_box.set_valign(Gtk.Align.START)

        middle_box = Gtk.Box(orientation=self.config.orientation, spacing=0)
        middle_box.set_halign(Gtk.Align.CENTER)
        middle_box.set_valign(Gtk.Align.CENTER)

        end_box = Gtk.Box(orientation=self.config.orientation, spacing=0)
        end_box.set_halign(Gtk.Align.END)
        end_box.set_valign(Gtk.Align.END)

        main_box = Gtk.Box(orientation=self.config.orientation, spacing=0)
        main_box.set_homogeneous(True)
        main_box.add(beginning_box)
        main_box.add(middle_box)
        main_box.add(end_box)

        for module in self._modules_beginning:
            beginning_box.add(module.widget())

        for module in self._modules_middle:
            middle_box.add(module.widget())

        for module in self._modules_end:
            end_box.add(module.widget())

        self._window = Gtk.Window(application=self, decorated=False)
        self._window.connect("destroy", Gtk.main_quit)
        self._window.add(main_box)

        GtkLayerShell.init_for_window(self._window)
        GtkLayerShell.auto_exclusive_zone_enable(self._window)
        self.update_anchors()

        self._window.show_all()

    def update_anchors(self):
        edges = []

        match self.config.position:
            case BarPosition.TOP:
                edges = [
                    GtkLayerShell.Edge.TOP,
                    GtkLayerShell.Edge.LEFT,
                    GtkLayerShell.Edge.RIGHT,
                ]
            case BarPosition.BOTTOM:
                edges = [
                    GtkLayerShell.Edge.BOTTOM,
                    GtkLayerShell.Edge.LEFT,
                    GtkLayerShell.Edge.RIGHT,
                ]
            case BarPosition.LEFT:
                edges = [
                    GtkLayerShell.Edge.TOP,
                    GtkLayerShell.Edge.BOTTOM,
                    GtkLayerShell.Edge.LEFT,
                ]
            case BarPosition.RIGHT:
                edges = [
                    GtkLayerShell.Edge.TOP,
                    GtkLayerShell.Edge.BOTTOM,
                    GtkLayerShell.Edge.RIGHT,
                ]

        for edge in edges:
            GtkLayerShell.set_anchor(self._window, edge, True)

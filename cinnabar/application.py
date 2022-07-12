from __future__ import annotations

import importlib
import inspect
import signal
from enum import Enum

import nestedtext
from gi.repository import Gio, GLib, Gtk, GtkLayerShell

from cinnabar.bar import Bar


class Application(Gtk.Application):
    _config: dict = {}

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

        self.add_main_option(
            "config",
            ord("c"),
            GLib.OptionFlags.NONE,
            GLib.OptionArg.STRING,
            "Config file to use",
        )

        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, self.quit)

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        options = command_line.get_options_dict()
        options = options.end().unpack()

        if "config" in options:
            with open(options["config"], "r") as f:
                loaded_config = nestedtext.load(f)
                if isinstance(loaded_config, dict):
                    self._config = loaded_config
                else:
                    raise RuntimeError("Invalid config file.")

        self.activate()
        return 0

    def do_activate(self) -> None:
        self._bar = Bar(self, self._config)

from __future__ import annotations

import signal

import nestedtext
from gi.repository import Gdk, Gio, GLib, Gtk

from cinnabar.bar import Bar


class Application(Gtk.Application):
    _bars: list[Bar] = []
    """List of bars being displayed (one per output)."""

    _config: dict = {}
    """Application configuration loaded from the config file."""

    _outputs: list[str] = []
    """List of outputs on which the bar should be displayed."""

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

    @property
    def outputs(self):
        if self._outputs:
            return self._outputs

        cfg_outputs: list[str] | str = self._config.get("output", [])
        if isinstance(cfg_outputs, str):
            cfg_outputs = [cfg_outputs]

        self._outputs = cfg_outputs
        return self._outputs

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
        display = Gdk.Display.get_default()

        if not isinstance(display, Gdk.Display):
            raise RuntimeError("No Wayland display connected.")

        monitor_count = display.get_n_monitors()
        for i in range(monitor_count):
            monitor = display.get_monitor(i)
            if monitor is not None:
                self.monitor_added(display, monitor)

        display.connect("monitor-added", self.monitor_added)
        display.connect("monitor-removed", self.monitor_removed)

    def monitor_added(self, display: Gdk.Display, monitor: Gdk.Monitor):
        monitor_idx = None
        monitor_count = display.get_n_monitors()
        for i in range(monitor_count):
            if display.get_monitor(i) == monitor:
                monitor_idx = i

        if monitor_idx is None:
            error = "Unable to get information for monitor: {} {}".format(
                monitor.get_manufacturer(),
                monitor.get_model(),
            )
            raise RuntimeError(error)

        output = display.get_default_screen().get_monitor_plug_name(
            monitor_idx
        )
        self._bars.append(Bar(self, monitor, output, self._config))

    def monitor_removed(self, _: Gdk.Display, monitor: Gdk.Monitor):
        monitor_idx = None
        for i in range(len(self._bars)):
            if self._bars[i].monitor == monitor:
                monitor_idx = i
                break

        if monitor_idx is not None:
            del self._bars[monitor_idx]

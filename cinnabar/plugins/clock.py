from datetime import datetime

from gi.repository import GObject, Gtk

from cinnabar.bar import Bar, WidgetPlugin


class Clock(WidgetPlugin):
    def __init__(self, _: Bar, config: dict) -> None:
        self._label = Gtk.Label()
        self._config = config
        self.update_clock()
        GObject.timeout_add(100, self.update_clock)

    def update_clock(self):
        clock_str = self._config["format"].format(datetime.now())
        self._label.set_label(clock_str)
        return True

    def widget(self) -> Gtk.Widget:
        return self._label

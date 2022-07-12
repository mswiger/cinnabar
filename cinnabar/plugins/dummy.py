from gi.repository import Gtk

from cinnabar.plugin import WidgetPlugin


class DummyModule(WidgetPlugin):
    def __init__(self, config: dict):
        return

    def widget(self) -> Gtk.Widget:
        return Gtk.Label(label="Hello")
